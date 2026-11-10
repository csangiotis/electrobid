import os
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from accounts.textsearch import matches

from . import events
from .boq_import import BOQImportError, parse_boq
from .comparison import build_comparison, comparison_xlsx
from .models import Bid, BidLine, BOQItem, Job, JobDocument, JobQuestion
from .serializers import (
    BidSerializer, BidWriteSerializer, BOQItemSerializer,
    BOQWriteItemSerializer, JobDetailSerializer, JobDocumentSerializer,
    JobListSerializer, JobWriteSerializer, MyBidListSerializer, QuestionSerializer,
)


def _require_contractor(user):
    if not user.is_contractor:
        raise PermissionDenied("Μόνο εργολάβοι μπορούν να κάνουν αυτή την ενέργεια.")


def _require_verified(user):
    if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
        raise PermissionDenied("Επιβεβαιώστε πρώτα το email σας (δείτε το email που σας στείλαμε).")


def _require_subcontractor(user):
    if not user.is_subcontractor:
        raise PermissionDenied("Μόνο υπεργολάβοι μπορούν να δίνουν προσφορές.")


class JobViewSet(viewsets.ModelViewSet):
    """
    Εργασίες. Η προεπιλεγμένη λίστα είναι το marketplace (ανοιχτές εργασίες).
    ?scope=mine επιστρέφει τις εργασίες του εργολάβου, σε όλες τις καταστάσεις.
    """

    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        user = self.request.user
        qs = Job.objects.select_related(
            "contractor__company", "awarded_bid__subcontractor__company"
        ).annotate(
            boq_count=Count("boq_items", filter=Q(boq_items__quantity__isnull=False), distinct=True),
            documents_count=Count("documents", distinct=True),
            bids_count=Count("bids", filter=Q(bids__status=Bid.Status.SUBMITTED), distinct=True),
            my_bid_status=Subquery(
                Bid.objects.filter(job=OuterRef("pk"), subcontractor=user).values("status")[:1]
            ),
        )
        if self.action != "list":
            # Τα πρόχειρα τα βλέπει μόνο ο ιδιοκτήτης.
            return qs.filter(Q(contractor=user) | ~Q(status=Job.Status.DRAFT))

        params = self.request.query_params
        if params.get("scope") == "mine":
            qs = qs.filter(contractor=user)
        else:
            qs = qs.filter(status=Job.Status.OPEN, bid_deadline__gt=timezone.now())
        if params.get("region"):
            qs = qs.filter(region=params["region"])
        if params.get("category"):
            qs = qs.filter(category=params["category"])
        # Φίλτρο ειδικότητας (JSON λίστα· φιλτράρεται στην Python για συμβατότητα με SQLite)
        wanted = set()
        mine = False
        if params.get("trade"):
            wanted = {params["trade"]}
        elif params.get("mine") in ("1", "true") and getattr(user, "company", None):
            wanted, mine = set(user.company.specialties or []), True
        if wanted:
            # Στο «μόνο τις δικές μου» εμφανίζονται και εργασίες χωρίς δηλωμένη ειδικότητα
            ids = [pk for pk, trades in qs.values_list("id", "trades")
                   if wanted & set(trades or []) or (mine and not trades)]
            qs = qs.filter(id__in=ids)
        if params.get("scope") != "mine":
            qs = qs.order_by("bid_deadline")
        if params.get("q"):
            # Αγνοεί κεφαλαία/τόνους· φιλτράρεται στην Python (μικρός όγκος ανοιχτών εργασιών)
            ids = [pk for pk, t, d, loc in qs.values_list("id", "title", "description", "location")
                   if matches(params["q"], t, d, loc)]
            qs = qs.filter(id__in=ids)
        return qs

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return JobWriteSerializer
        if self.action == "list":
            return JobListSerializer
        return JobDetailSerializer

    def _owned(self):
        job = self.get_object()
        if job.contractor_id != self.request.user.id:
            raise PermissionDenied("Η εργασία ανήκει σε άλλον εργολάβο.")
        return job

    # --- CRUD -------------------------------------------------------------
    def create(self, request, *args, **kwargs):
        _require_contractor(request.user)
        s = JobWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        job = s.save(contractor=request.user)
        return Response(JobDetailSerializer(job, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        job = self._owned()
        partial = kwargs.pop("partial", False)
        if job.status == Job.Status.OPEN:
            # Μετά τη δημοσίευση επιτρέπεται μόνο παράταση προθεσμίας.
            extra = set(request.data.keys()) - {"bid_deadline"}
            if extra:
                raise ValidationError(
                    "Η εργασία έχει δημοσιευτεί. Επιτρέπεται μόνο παράταση της προθεσμίας· "
                    "για αλλαγές ανεβάστε συμπλήρωμα."
                )
            new_deadline = JobWriteSerializer().fields["bid_deadline"].to_internal_value(
                request.data["bid_deadline"]
            )
            if job.bid_deadline and new_deadline <= job.bid_deadline:
                raise ValidationError("Η νέα προθεσμία πρέπει να είναι μεταγενέστερη.")
            if job.deadline_passed:
                raise ValidationError("Η προθεσμία έχει ήδη λήξει.")
        elif job.status != Job.Status.DRAFT:
            raise ValidationError("Η εργασία δεν μπορεί πλέον να αλλάξει.")
        s = JobWriteSerializer(job, data=request.data, partial=partial)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(JobDetailSerializer(self.get_object(), context={"request": request}).data)

    def destroy(self, request, *args, **kwargs):
        job = self._owned()
        if job.status != Job.Status.DRAFT:
            raise ValidationError("Διαγράφονται μόνο πρόχειρες εργασίες. Χρησιμοποιήστε ακύρωση.")
        job.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # --- Κύκλος ζωής ------------------------------------------------------
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        job = self._owned()
        if job.status != Job.Status.DRAFT:
            raise ValidationError("Η εργασία έχει ήδη δημοσιευτεί.")
        errors = []
        if not job.trades:
            errors.append("Επιλέξτε τουλάχιστον μία ειδικότητα.")
        if not job.boq_items.exclude(quantity=None).exists():
            errors.append("Προσθέστε προμέτρηση με τουλάχιστον μία γραμμή με ποσότητα.")
        if not job.bid_deadline or job.bid_deadline <= timezone.now() + timedelta(hours=1):
            errors.append("Ορίστε προθεσμία προσφορών τουλάχιστον μία ώρα από τώρα.")
        if errors:
            raise ValidationError({"detail": " ".join(errors)})
        _require_verified(request.user)
        job.status = Job.Status.OPEN
        job.published_at = timezone.now()
        job.save(update_fields=["status", "published_at", "updated_at"])
        events.job_published(job)
        return Response(JobDetailSerializer(self.get_object(), context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def close_bidding(self, request, pk=None):
        """Ο εργολάβος λήγει νωρίτερα την υποβολή προσφορών."""
        job = self._owned()
        if not job.accepts_bids:
            raise ValidationError("Η υποβολή προσφορών δεν είναι ανοιχτή.")
        job.bid_deadline = timezone.now()
        job.save(update_fields=["bid_deadline", "updated_at"])
        return Response(JobDetailSerializer(self.get_object(), context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        job = self._owned()
        if job.status not in (Job.Status.DRAFT, Job.Status.OPEN):
            raise ValidationError("Η εργασία δεν μπορεί να ακυρωθεί.")
        was_open = job.status == Job.Status.OPEN
        job.status = Job.Status.CANCELLED
        job.save(update_fields=["status", "updated_at"])
        if was_open:
            events.job_cancelled(job)
        return Response(JobDetailSerializer(self.get_object(), context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def award(self, request, pk=None):
        job = self._owned()
        if job.status != Job.Status.OPEN or not job.deadline_passed:
            raise ValidationError("Η ανάθεση γίνεται μετά τη λήξη της προθεσμίας.")
        bid = get_object_or_404(job.bids, pk=request.data.get("bid_id"),
                                status=Bid.Status.SUBMITTED)
        job.awarded_bid = bid
        job.status = Job.Status.AWARDED
        job.save(update_fields=["awarded_bid", "status", "updated_at"])
        events.job_awarded(job, [bid])
        return Response(JobDetailSerializer(self.get_object(), context={"request": request}).data)

    # --- Προμέτρηση -------------------------------------------------------
    @action(detail=True, methods=["get", "put"])
    def boq(self, request, pk=None):
        if request.method == "GET":
            job = self.get_object()
            return Response(BOQItemSerializer(job.boq_items.all(), many=True).data)
        job = self._owned()
        if job.status != Job.Status.DRAFT:
            raise ValidationError("Η προμέτρηση κλειδώνει μετά τη δημοσίευση.")
        s = BOQWriteItemSerializer(data=request.data, many=True)
        s.is_valid(raise_exception=True)
        self._replace_boq(job, s.validated_data)
        return Response(BOQItemSerializer(job.boq_items.all(), many=True).data)

    @action(detail=True, methods=["post"], url_path="boq/import")
    def import_boq(self, request, pk=None):
        job = self._owned()
        if job.status != Job.Status.DRAFT:
            raise ValidationError("Η προμέτρηση κλειδώνει μετά τη δημοσίευση.")
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError("Επιλέξτε αρχείο.")
        try:
            items = parse_boq(upload)
        except BOQImportError as exc:
            raise ValidationError(str(exc))
        self._replace_boq(job, items)
        if request.data.get("keep_file") in ("1", "true", "on"):
            upload.seek(0)
            self._store_document(job, upload, f"Προμέτρηση ({upload.name})", JobDocument.Kind.BOQ)
        return Response(BOQItemSerializer(job.boq_items.all(), many=True).data)

    @staticmethod
    @transaction.atomic
    def _replace_boq(job, items):
        job.boq_items.all().delete()
        BOQItem.objects.bulk_create([
            BOQItem(job=job, position=i, code=it.get("code", ""),
                    description=it["description"], unit=it.get("unit", "") if it.get("quantity") is not None else "",
                    quantity=it.get("quantity"))
            for i, it in enumerate(items, start=1)
        ])

    # --- Έγγραφα ----------------------------------------------------------
    @action(detail=True, methods=["get", "post"])
    def documents(self, request, pk=None):
        if request.method == "GET":
            job = self.get_object()
            return Response(JobDocumentSerializer(job.documents.all(), many=True).data)
        job = self._owned()
        if job.status not in (Job.Status.DRAFT, Job.Status.OPEN) or job.deadline_passed:
            raise ValidationError("Δεν μπορούν πλέον να προστεθούν έγγραφα.")
        files = request.FILES.getlist("files") or request.FILES.getlist("file")
        if not files:
            raise ValidationError("Επιλέξτε αρχείο.")
        kind = request.data.get("kind") or JobDocument.Kind.DRAWING
        if kind not in JobDocument.Kind.values:
            raise ValidationError("Άγνωστο είδος εγγράφου.")
        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in settings.ALLOWED_DOCUMENT_EXTENSIONS:
                raise ValidationError(f"Μη επιτρεπτός τύπος αρχείου: {f.name}")
            if f.size > settings.MAX_DOCUMENT_SIZE:
                raise ValidationError(f"Το αρχείο {f.name} ξεπερνά τα 50 MB.")
        title = (request.data.get("title") or "").strip()
        created = []
        with transaction.atomic():
            if job.status == Job.Status.OPEN:
                # Συμπλήρωμα: νέα αναθεώρηση της εργασίας
                job.revision += 1
                job.save(update_fields=["revision", "updated_at"])
            for f in files:
                doc_title = title if (title and len(files) == 1) else os.path.splitext(f.name)[0]
                created.append(self._store_document(job, f, doc_title, kind))
        if job.status == Job.Status.OPEN:
            events.addendum_added(job, len(created))
        return Response(JobDocumentSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _store_document(job, f, title, kind):
        prev = job.documents.filter(title=title).order_by("-version").first()
        return JobDocument.objects.create(
            job=job, file=f, title=title[:200], kind=kind,
            version=(prev.version + 1) if prev else 0,
            is_addendum=job.status == Job.Status.OPEN,
            job_revision=job.revision, size=f.size,
        )

    # --- Ερωτήσεις --------------------------------------------------------
    @action(detail=True, methods=["get", "post"])
    def questions(self, request, pk=None):
        job = self.get_object()
        ctx = {"request": request}
        if request.method == "GET":
            qs = job.questions.select_related("author__company", "job")
            if job.contractor_id != request.user.id:
                qs = qs.filter(~Q(answer="") | Q(author=request.user))
            return Response(QuestionSerializer(qs, many=True, context=ctx).data)
        if job.contractor_id == request.user.id:
            raise ValidationError("Ο εργολάβος απαντά σε ερωτήσεις, δεν τις υποβάλλει.")
        if not job.accepts_bids:
            raise ValidationError("Οι ερωτήσεις κλείνουν με τη λήξη της προθεσμίας.")
        text = (request.data.get("text") or "").strip()
        if len(text) < 5:
            raise ValidationError("Γράψτε την ερώτησή σας.")
        q = JobQuestion.objects.create(job=job, author=request.user, text=text)
        events.question_asked(q)
        return Response(QuestionSerializer(q, context=ctx).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path=r"questions/(?P<qid>\d+)/answer")
    def answer_question(self, request, pk=None, qid=None):
        job = self._owned()
        q = get_object_or_404(job.questions, pk=qid)
        answer = (request.data.get("answer") or "").strip()
        if not answer:
            raise ValidationError("Γράψτε απάντηση.")
        q.answer = answer
        q.answered_at = timezone.now()
        q.save(update_fields=["answer", "answered_at"])
        events.question_answered(q)
        return Response(QuestionSerializer(q, context={"request": request}).data)

    # --- Προσφορές (πλευρά εργολάβου) ---------------------------------------
    @action(detail=True, methods=["get"])
    def comparison(self, request, pk=None):
        job = self._owned()
        if job.status == Job.Status.OPEN and not job.deadline_passed:
            return Response({
                "sealed": True,
                "submitted_count": job.bids.filter(status=Bid.Status.SUBMITTED).count(),
                "drafts_count": job.bids.filter(status=Bid.Status.DRAFT).count(),
                "bid_deadline": job.bid_deadline,
            })
        data = build_comparison(job)
        data["awarded_bid_id"] = job.awarded_bid_id
        return Response(data)

    @action(detail=True, methods=["get"], url_path="comparison/export")
    def comparison_export(self, request, pk=None):
        job = self._owned()
        if job.status == Job.Status.OPEN and not job.deadline_passed:
            raise PermissionDenied("Οι προσφορές είναι σφραγισμένες μέχρι τη λήξη της προθεσμίας.")
        content = comparison_xlsx(job)
        resp = HttpResponse(
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="sygkrisi-ergasia-{job.id}.xlsx"'
        return resp

    # --- Προσφορές (πλευρά υπεργολάβου) -------------------------------------
    @action(detail=True, methods=["get", "put"], url_path="my-bid")
    def my_bid(self, request, pk=None):
        job = self.get_object()
        _require_subcontractor(request.user)
        bid = job.bids.filter(subcontractor=request.user).first()
        if request.method == "GET":
            return Response(BidSerializer(bid).data if bid else None)

        self._check_can_bid(job, request.user)
        s = BidWriteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        lines = data.pop("lines", None)
        with transaction.atomic():
            if bid is None:
                bid = Bid.objects.create(job=job, subcontractor=request.user)
            for k, v in data.items():
                setattr(bid, k, v)
            if bid.status == Bid.Status.WITHDRAWN:
                bid.status = Bid.Status.DRAFT
            if bid.status == Bid.Status.SUBMITTED:
                bid.submitted_at = timezone.now()
                bid.job_revision = job.revision
            bid.save()
            if lines is not None:
                valid_items = set(job.boq_items.exclude(quantity=None).values_list("id", flat=True))
                for ln in lines:
                    if ln["item"] not in valid_items:
                        raise ValidationError(f"Η γραμμή {ln['item']} δεν ανήκει στην προμέτρηση.")
                    BidLine.objects.update_or_create(
                        bid=bid, item_id=ln["item"],
                        defaults={"unit_price": ln.get("unit_price"), "note": ln.get("note", "")},
                    )
        return Response(BidSerializer(bid).data)

    @action(detail=True, methods=["post"], url_path="my-bid/submit")
    def submit_bid(self, request, pk=None):
        job = self.get_object()
        _require_subcontractor(request.user)
        self._check_can_bid(job, request.user)
        _require_verified(request.user)
        bid = get_object_or_404(job.bids, subcontractor=request.user)
        if not bid.lines.exclude(unit_price=None).exists():
            raise ValidationError("Συμπληρώστε τιμές πριν την υποβολή.")
        bid.status = Bid.Status.SUBMITTED
        bid.submitted_at = timezone.now()
        bid.job_revision = job.revision
        bid.save()
        return Response(BidSerializer(bid).data)

    @action(detail=True, methods=["post"], url_path="my-bid/withdraw")
    def withdraw_bid(self, request, pk=None):
        job = self.get_object()
        _require_subcontractor(request.user)
        if not job.accepts_bids:
            raise ValidationError("Η προθεσμία έχει λήξει· η προσφορά δεν αποσύρεται πλέον.")
        bid = get_object_or_404(job.bids, subcontractor=request.user)
        bid.status = Bid.Status.WITHDRAWN
        bid.save(update_fields=["status", "updated_at"])
        return Response(BidSerializer(bid).data)

    @staticmethod
    def _check_can_bid(job, user):
        if not job.accepts_bids:
            raise ValidationError("Η εργασία δεν δέχεται προσφορές.")


class DocumentViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = JobDocument.objects.select_related("job")

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        doc = self.get_object()
        job = doc.job
        if job.status == Job.Status.DRAFT and job.contractor_id != request.user.id:
            raise PermissionDenied()
        try:
            fh = doc.file.open("rb")
        except FileNotFoundError:
            return Response({"detail": "Το αρχείο δεν είναι πλέον διαθέσιμο στον server."}, status=404)
        return FileResponse(fh, as_attachment=request.query_params.get("inline") != "1", filename=doc.filename)

    def destroy(self, request, *args, **kwargs):
        doc = self.get_object()
        if doc.job.contractor_id != request.user.id:
            raise PermissionDenied()
        if doc.job.status != Job.Status.DRAFT:
            raise ValidationError("Μετά τη δημοσίευση τα έγγραφα δεν διαγράφονται· ανεβάστε νέα έκδοση.")
        doc.file.delete(save=False)
        doc.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyBidsViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = MyBidListSerializer

    def get_queryset(self):
        return (Bid.objects.filter(subcontractor=self.request.user)
                .select_related("job__contractor__company").order_by("-updated_at"))

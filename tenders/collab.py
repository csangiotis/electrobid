"""Μετά την ανάθεση: συνομιλία, αξιολογήσεις και συμφωνητικό υπεργολαβίας."""
import os
from decimal import Decimal

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from notify.models import Kind
from notify.service import notify

from .models import Job, Message, Review, boq_sections
from .serializers import company_brief

# Κριτήρια αξιολόγησης ανάλογα με το ποιος αξιολογεί
CRITERIA = {
    "contractor": [("quality", "Ποιότητα εργασιών"), ("timeliness", "Τήρηση χρόνων"), ("cooperation", "Συνεργασία")],
    "subcontractor": [("payments", "Συνέπεια πληρωμών"), ("organization", "Οργάνωση εργοταξίου"),
                      ("communication", "Επικοινωνία")],
}
ATTACHMENT_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".dwg", ".dxf", ".xlsx", ".docx", ".zip"}


def awarded_subs(job):
    return {a.bid.subcontractor_id: a for a in job.awards.select_related("bid__subcontractor__company")}


def _thread_user(job, request):
    """Επιστρέφει (subcontractor_id) της συνομιλίας που ζητά ο χρήστης, με έλεγχο δικαιωμάτων."""
    subs = awarded_subs(job)
    if request.user.id == job.contractor_id:
        sid = request.query_params.get("with") or request.data.get("with")
        try:
            sid = int(sid)
        except (TypeError, ValueError):
            raise ValidationError("Επιλέξτε συνομιλία.")
        if sid not in subs:
            raise PermissionDenied()
        return sid
    if request.user.id in subs:
        return request.user.id
    raise PermissionDenied("Η συνομιλία είναι διαθέσιμη μόνο στον εργολάβο και τους αναδόχους.")


def _msg(m, me):
    return {"id": m.id, "text": m.text, "mine": m.sender_id == me.id, "created_at": m.created_at,
            "read": m.read_at is not None,
            "attachment": os.path.basename(m.attachment.name) if m.attachment else None}


class CollaborationMixin:
    @action(detail=True, methods=["get"])
    def threads(self, request, pk=None):
        job = self.get_object()
        subs = awarded_subs(job)
        me = request.user
        if me.id != job.contractor_id and me.id not in subs:
            raise PermissionDenied()
        ids = list(subs) if me.id == job.contractor_id else [me.id]
        out = []
        for sid in ids:
            msgs = job.messages.filter(subcontractor_id=sid)
            last = msgs.last()
            other = subs[sid].bid.subcontractor if me.id == job.contractor_id else job.contractor
            out.append({
                "with": sid, "company": company_brief(other),
                "unread": msgs.filter(read_at=None).exclude(sender=me).count(),
                "last": _msg(last, me) if last else None,
            })
        return Response(out)

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        job = self.get_object()
        sid = _thread_user(job, request)
        thread = job.messages.filter(subcontractor_id=sid)
        me = request.user
        if request.method == "POST":
            text = (request.data.get("text") or "").strip()[:5000]
            f = request.FILES.get("attachment")
            if not text and not f:
                raise ValidationError("Γράψτε μήνυμα ή επισυνάψτε αρχείο.")
            if f:
                if os.path.splitext(f.name)[1].lower() not in ATTACHMENT_EXT:
                    raise ValidationError("Μη επιτρεπτός τύπος αρχείου.")
                if f.size > 25 * 1024 * 1024:
                    raise ValidationError("Το αρχείο ξεπερνά τα 25 MB.")
            # Ειδοποίηση μόνο αν ο παραλήπτης έχει διαβάσει τα προηγούμενα (όχι ένα email ανά μήνυμα)
            recipient_id = sid if me.id == job.contractor_id else job.contractor_id
            had_unread = thread.filter(read_at=None, sender=me).exists()
            m = Message.objects.create(job=job, subcontractor_id=sid, sender=me, text=text, attachment=f or "")
            if not had_unread:
                from django.contrib.auth import get_user_model

                recipient = get_user_model().objects.get(pk=recipient_id)
                sender_name = company_brief(me)["name"]
                url = f"#/jobs/{job.id}?tab=collab" + (f"&with={sid}" if recipient_id == job.contractor_id else "")
                notify([recipient], Kind.MESSAGE, f"Νέο μήνυμα: {job.title}",
                       f"{sender_name}: «{text[:300] or 'συνημμένο αρχείο'}»", url, "Απάντηση")
            return Response(_msg(m, me), status=status.HTTP_201_CREATED)
        thread.filter(read_at=None).exclude(sender=me).update(read_at=timezone.now())
        return Response([_msg(m, me) for m in thread])

    @action(detail=True, methods=["get"], url_path=r"messages/(?P<mid>\d+)/attachment")
    def message_attachment(self, request, pk=None, mid=None):
        job = self.get_object()
        m = get_object_or_404(job.messages, pk=mid)
        if request.user.id not in (job.contractor_id, m.subcontractor_id) or not m.attachment:
            raise PermissionDenied()
        try:
            fh = m.attachment.open("rb")
        except FileNotFoundError:
            return Response({"detail": "Το αρχείο δεν είναι πλέον διαθέσιμο."}, status=404)
        return FileResponse(fh, as_attachment=True, filename=os.path.basename(m.attachment.name))

    @action(detail=True, methods=["get", "post"])
    def reviews(self, request, pk=None):
        """GET: τι μπορεί να αξιολογήσει ο χρήστης σε αυτή την εργασία. POST: {target, criteria, comment}."""
        job = self.get_object()
        me = request.user
        subs = awarded_subs(job)
        if job.status != Job.Status.AWARDED or (me.id != job.contractor_id and me.id not in subs):
            raise PermissionDenied("Αξιολόγηση γίνεται μόνο μετά από ανάθεση, μεταξύ εργολάβου και αναδόχων.")
        role = "contractor" if me.id == job.contractor_id else "subcontractor"
        targets = ([a.bid.subcontractor.company for a in subs.values()] if role == "contractor"
                   else [job.contractor.company])
        if request.method == "POST":
            target = next((c for c in targets if c.id == int(request.data.get("target") or 0)), None)
            if not target:
                raise ValidationError("Μη έγκυρη εταιρεία προς αξιολόγηση.")
            crit = request.data.get("criteria") or {}
            values = {}
            for key, _ in CRITERIA[role]:
                try:
                    v = int(crit.get(key))
                except (TypeError, ValueError):
                    raise ValidationError("Βαθμολογήστε όλα τα κριτήρια (1 έως 5).")
                if not 1 <= v <= 5:
                    raise ValidationError("Η βαθμολογία είναι από 1 έως 5.")
                values[key] = v
            rating = round(sum(values.values()) / len(values))
            review, created = Review.objects.update_or_create(
                job=job, author=me, target=target,
                defaults={"criteria": values, "rating": rating,
                          "comment": (request.data.get("comment") or "").strip()[:2000]})
            if created:
                notify([target.user], Kind.REVIEW, f"Νέα αξιολόγηση: {job.title}",
                       f"Η εταιρεία {company_brief(me)['name']} σας αξιολόγησε με {rating}/5.",
                       f"#/companies/{target.id}", "Δείτε το προφίλ σας")
        existing = {r.target_id: r for r in Review.objects.filter(job=job, author=me)}
        return Response({
            "criteria": [{"key": k, "label": label} for k, label in CRITERIA[role]],
            "targets": [{
                "company": company_brief(c.user),
                "review": ({"rating": existing[c.id].rating, "criteria": existing[c.id].criteria,
                            "comment": existing[c.id].comment} if c.id in existing else None),
            } for c in targets],
        })

    @action(detail=True, methods=["get"])
    def contract(self, request, pk=None):
        """Στοιχεία για το ιδιωτικό συμφωνητικό υπεργολαβίας (?bid=<id> για τον εργολάβο)."""
        job = self.get_object()
        subs = awarded_subs(job)
        me = request.user
        if me.id == job.contractor_id:
            try:
                award = next(a for a in subs.values() if a.bid_id == int(request.query_params.get("bid") or 0))
            except StopIteration:
                raise ValidationError("Επιλέξτε ανάδοχο.")
        elif me.id in subs:
            award = subs[me.id]
        else:
            raise PermissionDenied()
        bid = award.bid
        sections = boq_sections(list(job.boq_items.all()))
        scope = set(award.sections) or {sid for sid, *_ in sections}
        prices = {ln.item_id: ln for ln in bid.lines.all()}
        appendix = []
        for sid, code, title, items in sections:
            if sid not in scope:
                continue
            rows = []
            for it in items:
                ln = prices.get(it.id)
                up = ln.unit_price if ln else None
                rows.append({"code": it.code, "description": it.description, "unit": it.unit,
                             "quantity": it.quantity, "unit_price": up,
                             "total": (up * it.quantity).quantize(Decimal("0.01")) if up is not None else None})
            appendix.append({"code": code, "title": title, "rows": rows})

        def party(user):
            c = user.company
            return {"name": c.name, "vat_number": c.vat_number, "tax_office": c.tax_office, "address": c.address,
                    "city": c.city, "phone": c.phone, "email": user.email,
                    "representative": f"{user.first_name} {user.last_name}".strip()}

        vat = (award.amount * Decimal("0.24")).quantize(Decimal("0.01"))
        return Response({
            "job": {"id": job.id, "title": job.title, "location": job.location, "region": job.get_region_display(),
                    "description": job.description, "start_date": job.start_date, "duration_text": job.duration_text},
            "contractor": party(job.contractor),
            "subcontractor": party(bid.subcontractor),
            "scope": [title for sid, _, title, _ in sections if sid in scope] if award.sections else [],
            "amount": award.amount, "vat_24": vat, "amount_with_vat": award.amount + vat,
            "duration_days": bid.duration_days, "payment_terms": bid.payment_terms,
            "exclusions": bid.exclusions, "awarded_at": award.created_at,
            "appendix": appendix,
        })


def company_reviews(company):
    """Δημόσια σύνοψη αξιολογήσεων εταιρείας για το προφίλ της."""
    qs = list(Review.objects.filter(target=company).select_related("author__company", "job"))
    if not qs:
        return {"count": 0, "average": None, "criteria": {}, "items": []}
    crit = {}
    for r in qs:
        for k, v in r.criteria.items():
            crit.setdefault(k, []).append(v)
    labels = dict(CRITERIA["contractor"] + CRITERIA["subcontractor"])
    return {
        "count": len(qs),
        "average": round(sum(r.rating for r in qs) / len(qs), 1),
        "criteria": {k: {"label": labels.get(k, k), "average": round(sum(v) / len(v), 1)} for k, v in crit.items()},
        "items": [{"rating": r.rating, "comment": r.comment, "created_at": r.created_at,
                   "author": r.author.company.name if hasattr(r.author, "company") else "",
                   "job": r.job.title} for r in qs[:30]],
    }


def ratings_for(company_ids):
    """{company_id: (μέσος όρος, πλήθος)} για τις κάρτες του καταλόγου."""
    from django.db.models import Avg, Count

    rows = (Review.objects.filter(target_id__in=company_ids).values("target_id")
            .annotate(avg=Avg("rating"), n=Count("id")))
    return {r["target_id"]: (round(r["avg"], 1), r["n"]) for r in rows}


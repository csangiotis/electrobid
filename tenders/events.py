"""Ειδοποιήσεις που προκαλούνται από γεγονότα στις εργασίες."""
from django.contrib.auth import get_user_model

from notify.models import Kind
from notify.service import notify

from .models import Bid

User = get_user_model()


def _company(user):
    c = getattr(user, "company", None)
    return c.name if c else user.email


def _participants(job):
    """Υπεργολάβοι που ασχολούνται με την εργασία: έχουν προσφορά (κάθε κατάσταση) ή ερώτηση."""
    ids = set(job.bids.exclude(status=Bid.Status.WITHDRAWN).values_list("subcontractor_id", flat=True))
    ids |= set(job.questions.values_list("author_id", flat=True))
    return list(User.objects.filter(id__in=ids).exclude(id=job.contractor_id))


def matching_subcontractors(job):
    """Υπεργολάβοι με ειδικότητα της εργασίας που δραστηριοποιούνται στην περιοχή της."""
    subs = User.objects.filter(role=User.Role.SUBCONTRACTOR, is_active=True).select_related("company")
    wanted = set(job.trades or [])
    out = []
    for u in subs:
        c = getattr(u, "company", None)
        if not c:
            continue
        in_region = c.region == job.region or job.region in (c.service_regions or [])
        if in_region and (not wanted or wanted & set(c.specialties or [])):
            out.append(u)
    return out


def job_published(job):
    if getattr(job, "visibility", "public") != "public":
        return
    where = job.location or job.get_region_display()
    notify(matching_subcontractors(job), Kind.NEW_JOB, f"Νέα εργασία: {job.title}",
           f"Ο εργολάβος {_company(job.contractor)} ζητά προσφορές για «{job.title}» ({where}).\n\n"
           f"Προθεσμία υποβολής: {job.bid_deadline:%d/%m/%Y %H:%M}.",
           f"#/jobs/{job.id}", "Δείτε την εργασία")


def addendum_added(job, count):
    notify(_participants(job), Kind.ADDENDUM, f"Συμπλήρωμα: {job.title}",
           f"Προστέθηκαν {count} νέα έγγραφα στην εργασία «{job.title}». "
           "Ελέγξτε τα πριν υποβάλετε ή ενημερώσετε την προσφορά σας.",
           f"#/jobs/{job.id}", "Δείτε τα έγγραφα")


def question_asked(question):
    job = question.job
    notify([job.contractor], Kind.QA, f"Νέα ερώτηση: {job.title}",
           f"«{question.text[:300]}»\n\nΗ απάντησή σας θα δημοσιευτεί σε όλους τους υπεργολάβους.",
           f"#/jobs/{job.id}?tab=qa", "Απάντηση")


def question_answered(question):
    job = question.job
    notify(_participants(job), Kind.QA, f"Νέα απάντηση: {job.title}",
           f"Ερώτηση: «{question.text[:300]}»\n\nΑπάντηση: «{question.answer[:600]}»",
           f"#/jobs/{job.id}?tab=qa", "Δείτε τις διευκρινίσεις")


def job_awarded(job, awarded_bids):
    winners = {b.subcontractor_id for b in awarded_bids}
    for b in awarded_bids:
        scope = getattr(b, "_award_scope", "")
        notify([b.subcontractor], Kind.AWARD, f"Σας ανατέθηκε: {job.title}",
               f"Ο εργολάβος {_company(job.contractor)} σας ανέθεσε την εργασία «{job.title}»{scope}. "
               "Μπορείτε να επικοινωνήσετε από τη σελίδα της εργασίας.",
               f"#/jobs/{job.id}", "Άνοιγμα εργασίας")
    others = User.objects.filter(
        id__in=job.bids.filter(status=Bid.Status.SUBMITTED).exclude(subcontractor_id__in=winners)
        .values_list("subcontractor_id", flat=True))
    notify(list(others), Kind.AWARD, f"Αποτέλεσμα: {job.title}",
           f"Η εργασία «{job.title}» ανατέθηκε σε άλλον υπεργολάβο. Ευχαριστούμε για την προσφορά σας.",
           f"#/jobs/{job.id}", "Άνοιγμα εργασίας")


def job_cancelled(job):
    notify(_participants(job), Kind.AWARD, f"Ακυρώθηκε: {job.title}",
           f"Ο εργολάβος ακύρωσε την εργασία «{job.title}».", f"#/jobs/{job.id}")


def send_pending_invitations(job):
    """Στέλνει τις προσκλήσεις που δεν έχουν ειδοποιηθεί (μόνο όταν η εργασία είναι δημοσιευμένη)."""
    if job.status != "open":
        return
    pending = list(job.invitations.filter(notified=False).select_related("company__user"))
    for inv in pending:
        extra = f"\n\nΜήνυμα: «{inv.message}»" if inv.message else ""
        notify([inv.company.user], Kind.INVITATION, f"Πρόσκληση: {job.title}",
               f"Ο εργολάβος {_company(job.contractor)} σας προσκαλεί να δώσετε προσφορά για «{job.title}» "
               f"({job.location or job.get_region_display()}). Προθεσμία: {job.bid_deadline:%d/%m/%Y %H:%M}.{extra}",
               f"#/jobs/{job.id}", "Δείτε την εργασία")
    job.invitations.filter(id__in=[i.id for i in pending]).update(notified=True)


def invitation_declined(inv):
    job = inv.job
    notify([job.contractor], Kind.INVITATION, f"Απόρριψη πρόσκλησης: {job.title}",
           f"Η εταιρεία {inv.company.name} δεν θα δώσει προσφορά για «{job.title}».",
           f"#/jobs/{job.id}?tab=invites")


def bafo_requested(job, bids):
    msg = f"\n\nΜήνυμα εργολάβου: «{job.bafo_message}»" if job.bafo_message else ""
    notify([b.subcontractor for b in bids], Kind.BAFO, f"Βελτιωμένη προσφορά: {job.title}",
           f"Ο εργολάβος {_company(job.contractor)} σας ζητά βελτιωμένη τελική προσφορά για «{job.title}». "
           f"Μπορείτε να αναθεωρήσετε τις τιμές σας έως {job.bafo_deadline:%d/%m/%Y %H:%M}.{msg}",
           f"#/jobs/{job.id}?tab=bid", "Αναθεώρηση προσφοράς")

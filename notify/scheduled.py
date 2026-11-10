"""
Περιοδικές εργασίες: υπενθύμιση 24 ωρών πριν τη λήξη και ειδοποίηση εργολάβου για άνοιγμα προσφορών.
Τρέχουν μέσω του ScheduledTasksMiddleware (το πολύ κάθε 10 λεπτά) ή με
`python manage.py run_scheduled` από cron.
"""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Kind, SchedulerState
from .service import notify

INTERVAL = timedelta(minutes=10)


def run(now=None):
    from tenders.models import Bid, Job

    now = now or timezone.now()
    sent = 0
    soon = Job.objects.filter(status=Job.Status.OPEN, reminder_sent=False,
                              bid_deadline__gt=now, bid_deadline__lte=now + timedelta(hours=24))
    for job in soon:
        drafts = [b.subcontractor for b in job.bids.filter(status=Bid.Status.DRAFT).select_related("subcontractor")]
        notify(drafts, Kind.DEADLINE, f"Λήγει σε λιγότερο από 24 ώρες: {job.title}",
               f"Η προσφορά σας για «{job.title}» είναι ακόμα πρόχειρη. "
               f"Η προθεσμία λήγει {timezone.localtime(job.bid_deadline):%d/%m/%Y %H:%M}.",
               f"#/jobs/{job.id}?tab=bid", "Ολοκλήρωση προσφοράς")
        job.reminder_sent = True
        job.save(update_fields=["reminder_sent"])
        sent += len(drafts)

    opened = Job.objects.filter(status=Job.Status.OPEN, opened_notified=False, bid_deadline__lte=now)
    for job in opened:
        n = job.bids.filter(status=Bid.Status.SUBMITTED).count()
        notify([job.contractor], Kind.BIDS, f"Άνοιξαν οι προσφορές: {job.title}",
               f"Η προθεσμία έληξε με {n} {'προσφορά' if n == 1 else 'προσφορές'}. "
               "Δείτε τη σύγκριση και αποφασίστε την ανάθεση.",
               f"#/jobs/{job.id}?tab=bids", "Σύγκριση προσφορών")
        job.opened_notified = True
        job.save(update_fields=["opened_notified"])
        sent += 1
    bafo_done = Job.objects.filter(status=Job.Status.OPEN, bafo_deadline__lte=now, bafo_closed_notified=False)
    for job in bafo_done:
        n = job.bids.filter(bafo_invited=True, bafo_submitted_at__isnull=False).count()
        notify([job.contractor], Kind.BAFO, f"Έληξε το BAFO: {job.title}",
               f"Ο γύρος βελτιωμένων προσφορών έληξε. Αναθεώρησαν {n} υπεργολάβοι. "
               "Δείτε την τελική σύγκριση.", f"#/jobs/{job.id}?tab=bids", "Σύγκριση")
        job.bafo_closed_notified = True
        job.save(update_fields=["bafo_closed_notified"])
        sent += 1
    return sent


def tick():
    """Τρέχει το run() αν πέρασαν 10 λεπτά από την τελευταία φορά.
    Η ενημέρωση με συνθήκη εξασφαλίζει ότι μόνο ένας worker θα το τρέξει."""
    now = timezone.now()
    SchedulerState.objects.get_or_create(pk=1)
    due = Q(last_run__isnull=True) | Q(last_run__lte=now - INTERVAL)
    if SchedulerState.objects.filter(due, pk=1).update(last_run=now):
        run(now)

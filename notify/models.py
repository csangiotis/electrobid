from django.conf import settings
from django.db import models


class Kind(models.TextChoices):
    NEW_JOB = "new_job", "Νέες εργασίες στις ειδικότητές μου"
    INVITATION = "invitation", "Προσκλήσεις σε εργασίες"
    ADDENDUM = "addendum", "Συμπληρώματα εργασιών"
    QA = "qa", "Ερωτήσεις και απαντήσεις"
    DEADLINE = "deadline", "Υπενθυμίσεις προθεσμίας"
    BIDS = "bids", "Άνοιγμα προσφορών"
    BAFO = "bafo", "Αιτήματα βελτιωμένης προσφοράς"
    AWARD = "award", "Αποτελέσματα ανάθεσης"
    MESSAGE = "message", "Μηνύματα"
    REVIEW = "review", "Αξιολογήσεις"


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=200, blank=True)  # διαδρομή frontend, π.χ. #/jobs/4
    read_at = models.DateTimeField(null=True, blank=True)
    emailed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"])]


class SchedulerState(models.Model):
    """Μία γραμμή: πότε έτρεξαν τελευταία φορά οι προγραμματισμένες εργασίες."""
    last_run = models.DateTimeField(null=True, blank=True)

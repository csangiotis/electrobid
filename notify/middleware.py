import logging

from . import scheduled

log = logging.getLogger(__name__)


class ScheduledTasksMiddleware:
    """Μετά από αιτήματα API τρέχει, το πολύ κάθε 10 λεπτά, τις αυτόματες ειδοποιήσεις.
    Έτσι δουλεύουν και σε server χωρίς cron (π.χ. δωρεάν πλάνο Render)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            try:
                scheduled.tick()
            except Exception:
                log.exception("Σφάλμα στις προγραμματισμένες εργασίες")
        return response

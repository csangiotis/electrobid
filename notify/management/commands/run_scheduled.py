from django.core.management.base import BaseCommand

from notify import scheduled


class Command(BaseCommand):
    help = "Στέλνει υπενθυμίσεις προθεσμίας και ειδοποιήσεις ανοίγματος προσφορών"

    def handle(self, *args, **opts):
        self.stdout.write(f"Στάλθηκαν {scheduled.run()} ειδοποιήσεις.")

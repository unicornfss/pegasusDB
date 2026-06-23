from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run frequent background jobs (for Render cron — not the web process)."

    def handle(self, *args, **options):
        jobs = (
            ("update_booking_statuses", {}),
            ("purge_dummy_bookings", {"verbosity": 0}),
            ("send_departure_reminders", {"verbosity": 0}),
            ("send_upcoming_booking_reminders", {"verbosity": 0}),
        )
        for name, kwargs in jobs:
            try:
                call_command(name, **kwargs)
                self.stdout.write(self.style.SUCCESS(f"OK: {name}"))
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"FAILED: {name}: {exc}"))

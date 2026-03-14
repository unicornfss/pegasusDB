from django.core.management.base import BaseCommand
from django.db.utils import OperationalError, ProgrammingError

from unicorn_project.training.services.dummy_bookings import purge_expired_dummy_bookings


class Command(BaseCommand):
    help = "Delete dummy / familiarisation bookings older than 7 days, including linked records."

    def handle(self, *args, **options):
        try:
            deleted = purge_expired_dummy_bookings(max_age_days=7)
        except (OperationalError, ProgrammingError) as exc:
            self.stdout.write(self.style.WARNING(f"Skipped dummy booking purge until migrations are applied: {exc}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired dummy booking(s)."))
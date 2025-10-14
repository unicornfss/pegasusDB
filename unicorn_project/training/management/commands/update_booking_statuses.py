from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q, Max, Min

from ...services.booking_status import auto_update_booking_statuses
from ...models import Booking  # for debug-only queries

class Command(BaseCommand):
    help = "Advance Booking statuses (scheduled → in_progress → awaiting_closure)."

    def add_arguments(self, parser):
        parser.add_argument("--quiet", action="store_true", help="Suppress output")
        parser.add_argument("--debug", action="store_true", help="Print diagnostics")

    def handle(self, *args, **opts):
        now = timezone.localtime()
        today, now_t = now.date(), now.time()

        if opts["debug"]:
            # Show what *would* move
            can_in_progress = (
                Booking.objects.filter(status="scheduled")
                .filter(Q(days__date=today, days__start_time__lte=now_t))
                .count()
            )
            pool = (
                Booking.objects.filter(status__in=["scheduled", "in_progress"])
                .annotate(first_day=Min("days__date"), last_day=Max("days__date"))
                .count()
            )
            self.stdout.write(f"Now local: {now}")
            self.stdout.write(f"Candidates to go in_progress: {can_in_progress}")
            self.stdout.write(f"Pool for awaiting_closure (sched/in_prog): {pool}")

        updated = auto_update_booking_statuses()

        if not opts["quiet"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{timezone.now().isoformat()}] Updated {updated} bookings."
                )
            )

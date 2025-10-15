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

        if opts.get("debug"):
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

        result = auto_update_booking_statuses()

        # Support both return styles: (n_in_prog, n_await) or just n_await
        if isinstance(result, tuple) and len(result) == 2:
            n_in_prog, n_await = result
        else:
            n_in_prog, n_await = None, int(result or 0)

        if not opts.get("quiet"):
            if n_in_prog is None:
                msg = f"[{timezone.now().isoformat()}] Updated {n_await} bookings to awaiting_closure."
            else:
                msg = (f"[{timezone.now().isoformat()}] "
                       f"Moved {n_in_prog} → in_progress, {n_await} → awaiting_closure.")
            self.stdout.write(self.style.SUCCESS(msg))

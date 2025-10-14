import math
from datetime import datetime, time, timedelta
from django.db.models import Q, Max, Min
from django.utils import timezone

from ..models import Booking

# If 0.02 day ≈ ~30 minutes, treat 1 day as 24 hours:
HOURS_PER_DAY = 24.0

def _add_hours_to_time(t: time, hours_float: float) -> time:
    base = datetime(2000, 1, 1, t.hour or 0, t.minute or 0)
    end  = base + timedelta(seconds=round(hours_float * 3600))
    return time(end.hour, end.minute)

def _hours_for_day_index(i: int, total_days: float, rows: int) -> float:
    whole = int(total_days)
    frac  = max(0.0, total_days - whole)
    if rows == 1:
        return max(0.0, total_days) * HOURS_PER_DAY
    if i <= whole:
        return HOURS_PER_DAY
    if frac > 0 and i == whole + 1:
        return frac * HOURS_PER_DAY
    return HOURS_PER_DAY

def auto_update_booking_statuses() -> int:
    """
    1) scheduled -> in_progress when today's start time has passed
    2) scheduled/in_progress -> awaiting_closure after the FINAL day's end has passed
       (if end_time is missing, compute from start_time + duration_days; never close before start
        and never close if computed duration is zero/invalid)
    Returns: count of rows updated to awaiting_closure (for logging).
    """
    now = timezone.localtime()
    today = now.date()
    now_t = now.time()
    tz = timezone.get_current_timezone()

    # 1) Scheduled -> In progress
    (Booking.objects
        .filter(status="scheduled")
        .filter(Q(days__date=today, days__start_time__lte=now_t))
        .update(status="in_progress")
    )

    # 2) -> Awaiting closure after final day ends
    qs = (Booking.objects
          .filter(status__in=["scheduled", "in_progress"])
          .annotate(first_day=Min("days__date"), last_day=Max("days__date")))

    SAFE_LATE_END = time(23, 59, 59)
    updated = 0

    for b in qs:
        if not b.last_day:
            continue
        if today < b.last_day:
            continue

        # Find day rows and the last-day row
        day_rows = list(b.days.all().order_by("date"))
        last_row = next((d for d in reversed(day_rows) if d.date == b.last_day), None)
        if not last_row:
            continue

        start_t = getattr(last_row, "start_time", None)
        end_t   = getattr(last_row, "end_time", None)

        # Never close before start time on the last day
        if today == b.last_day and start_t and now_t < start_t:
            continue

        # If no end time, compute from duration (with safety guards)
        if not end_t:
            total_days = float(getattr(b.course_type, "duration_days", 1.0) or 1.0)
            rows = max(1, math.ceil(total_days))
            try:
                day_index = day_rows.index(last_row) + 1
            except ValueError:
                day_index = rows

            if start_t:
                per_day_hours = _hours_for_day_index(day_index, total_days, rows)
                # Guard: zero/negative/None duration -> don't close early
                if per_day_hours and per_day_hours > 0:
                    end_t = _add_hours_to_time(start_t, per_day_hours)
                else:
                    end_t = SAFE_LATE_END
            else:
                # No start -> can't compute; never close early
                end_t = SAFE_LATE_END

        # Extra safety: if end <= start on the last day, push to late night
        if today == b.last_day and start_t and end_t <= start_t:
            end_t = SAFE_LATE_END

        last_dt = timezone.make_aware(datetime.combine(b.last_day, end_t), tz)
        if now >= last_dt and b.status in ("scheduled", "in_progress"):
            b.status = "awaiting_closure"
            b.save(update_fields=["status"])
            updated += 1

    return updated

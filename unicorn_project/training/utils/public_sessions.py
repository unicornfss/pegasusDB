"""Helpers for public register/feedback when multiple sessions share a course+date."""

from django.conf import settings
from django.db.models import Q

from ..models import BookingDay

_ACTIVE_BOOKING_STATUSES = ("scheduled", "in_progress", "awaiting_closure", "completed")


def _register_dev_mode() -> bool:
    return getattr(settings, "REGISTER_SHOW_DATE", settings.DEBUG)


def _active_booking_day_qs():
    qs = BookingDay.objects.all()
    if not _register_dev_mode():
        qs = qs.filter(booking__status__in=_ACTIVE_BOOKING_STATUSES)
    return qs


def matching_booking_days(course, day_date, instructor=None):
    """BookingDay rows for course on date, optionally filtered to one instructor."""
    if not course or not day_date:
        return []
    qs = (
        _active_booking_day_qs()
        .filter(booking__course_type=course, date=day_date)
        .select_related("booking", "instructor", "booking__instructor")
    )
    if instructor:
        qs = qs.filter(Q(booking__instructor=instructor) | Q(instructor=instructor))
    return list(qs.order_by("start_time", "id"))


def public_session_label(booking_day: BookingDay) -> str:
    """Human label for AM/PM (or timed) sessions on the public forms."""
    if booking_day.start_time:
        t = booking_day.start_time
        period = "Morning" if t.hour < 12 else "Afternoon"
        label = f"{period} session — {t.strftime('%H:%M')}"
        if booking_day.end_time:
            label += f" to {booking_day.end_time.strftime('%H:%M')}"
        return label
    ref = ""
    if booking_day.booking_id and booking_day.booking.course_reference:
        ref = booking_day.booking.course_reference
    return f"Session {ref}" if ref else "Session"


def session_choices(course, day_date, instructor):
    """List of {day_code, label, booking_day} for templates."""
    return [
        {
            "day_code": bd.day_code,
            "label": public_session_label(bd),
            "booking_day": bd,
        }
        for bd in matching_booking_days(course, day_date, instructor)
    ]


def resolve_booking_day(course, day_date, instructor, *, day_code="", instructor_fallback=False):
    """
    Pick the BookingDay for a public submission.
    Returns None if ambiguous (multiple sessions, no day_code) or no match.
    """
    if not course or not day_date:
        return None

    if instructor_fallback or not instructor:
        days = matching_booking_days(course, day_date, instructor=None)
        if day_code:
            for bd in days:
                if bd.day_code == day_code:
                    return bd
            return None
        return days[0] if days else None

    days = matching_booking_days(course, day_date, instructor)
    if not days:
        return None
    if day_code:
        for bd in days:
            if bd.day_code == day_code:
                return bd
        return None
    if len(days) == 1:
        return days[0]
    return None

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.conf import settings
from django.utils import timezone

from ..models import Booking, BookingDay, TelegramNotification
from .telegram_today import first_day_start_for_booking

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ("scheduled", "in_progress")
_DEPARTURE_TYPE = "departure_reminder"
_REMINDER_WINDOW = timedelta(minutes=6)


@dataclass(frozen=True)
class DepartureSession:
    booking: Booking
    on_date: datetime.date
    start_time: time
    booking_day: BookingDay | None = None
    morning_today: bool = False


def _buffer_minutes() -> int:
    try:
        return max(0, int(getattr(settings, "DEPARTURE_REMINDER_BUFFER_MINUTES", 30)))
    except (TypeError, ValueError):
        return 30


def _morning_today_time() -> time:
    raw = (getattr(settings, "DEPARTURE_MORNING_TODAY_TIME", "") or "07:00").strip()
    try:
        hour, minute = raw.split(":", 1)
        return time(int(hour), int(minute))
    except (TypeError, ValueError):
        return time(7, 0)


def is_first_course_day(booking, on_date) -> bool:
    first_date, _ = first_day_start_for_booking(booking)
    return bool(first_date and first_date == on_date)


def has_google_travel_duration(booking) -> bool:
    return bool(booking.travel_duration_seconds)


def uses_morning_today_reminder(booking, on_date) -> bool:
    if booking.allow_accommodation and is_first_course_day(booking, on_date):
        return True
    if not has_google_travel_duration(booking):
        return True
    return False


def should_send_departure_for_day(booking, booking_day: BookingDay | None, on_date) -> bool:
    if booking.allow_accommodation:
        return is_first_course_day(booking, on_date)
    return True


def departure_reminder_at(booking, on_date, start_time: time, *, morning_today: bool) -> datetime | None:
    if morning_today:
        return timezone.make_aware(datetime.combine(on_date, _morning_today_time()))

    if not start_time or not has_google_travel_duration(booking):
        return timezone.make_aware(datetime.combine(on_date, _morning_today_time()))

    travel = int(booking.travel_duration_seconds)
    buffer = timedelta(minutes=_buffer_minutes())
    start_dt = timezone.make_aware(datetime.combine(on_date, start_time))
    return start_dt - timedelta(seconds=travel) - buffer


def _already_sent(booking, booking_day: BookingDay | None, on_date) -> bool:
    if booking_day and booking_day.departure_reminder_sent_at:
        return True
    if booking_day is None:
        return TelegramNotification.objects.filter(
            booking=booking,
            notification_type=_DEPARTURE_TYPE,
            success=True,
            sent_at__date=on_date,
        ).exists()
    return False


def _mark_sent(booking_day: BookingDay | None):
    if booking_day:
        booking_day.departure_reminder_sent_at = timezone.now()
        booking_day.save(update_fields=["departure_reminder_sent_at"])


def sessions_for_date(on_date=None) -> list[DepartureSession]:
    on_date = on_date or timezone.localdate()
    sessions: list[DepartureSession] = []
    seen_booking_ids: set = set()

    day_rows = (
        BookingDay.objects.filter(
            date=on_date,
            booking__status__in=_ACTIVE_STATUSES,
            booking__instructor__isnull=False,
        )
        .select_related(
            "booking",
            "booking__instructor",
            "booking__course_type",
            "booking__business",
            "booking__training_location",
        )
        .prefetch_related("booking__days")
        .order_by("start_time", "booking__start_time")
    )
    for day in day_rows:
        booking = day.booking
        if not should_send_departure_for_day(booking, day, on_date):
            continue
        start = day.start_time or booking.start_time
        morning_today = uses_morning_today_reminder(booking, on_date)
        if not morning_today and not start:
            continue
        sessions.append(
            DepartureSession(
                booking=booking,
                on_date=on_date,
                start_time=start or _morning_today_time(),
                booking_day=day,
                morning_today=morning_today,
            )
        )
        seen_booking_ids.add(booking.pk)

    orphan_bookings = (
        Booking.objects.filter(
            course_date=on_date,
            status__in=_ACTIVE_STATUSES,
            instructor__isnull=False,
        )
        .exclude(pk__in=seen_booking_ids)
        .select_related("instructor", "course_type", "business", "training_location")
        .prefetch_related("days")
    )
    for booking in orphan_bookings:
        if not should_send_departure_for_day(booking, None, on_date):
            continue
        morning_today = uses_morning_today_reminder(booking, on_date)
        if not morning_today and not booking.start_time:
            continue
        sessions.append(
            DepartureSession(
                booking=booking,
                on_date=on_date,
                start_time=booking.start_time or _morning_today_time(),
                booking_day=None,
                morning_today=morning_today,
            )
        )
    return sessions


def due_departure_sessions(now=None) -> list[DepartureSession]:
    now = now or timezone.localtime()
    on_date = now.date()
    due: list[DepartureSession] = []

    for session in sessions_for_date(on_date):
        reminder_at = departure_reminder_at(
            session.booking,
            session.on_date,
            session.start_time,
            morning_today=session.morning_today,
        )
        if not reminder_at:
            continue
        if _already_sent(session.booking, session.booking_day, on_date):
            continue

        if session.morning_today:
            if reminder_at <= now < reminder_at + _REMINDER_WINDOW:
                due.append(session)
            continue

        start_dt = timezone.make_aware(datetime.combine(session.on_date, session.start_time))
        if reminder_at <= now < start_dt:
            due.append(session)
    return due


def send_due_departure_reminders(*, now=None) -> int:
    from .booking_notifications import notify_departure_reminder

    sent = 0
    for session in due_departure_sessions(now=now):
        try:
            if notify_departure_reminder(
                session.booking,
                on_date=session.on_date,
                morning_today=session.morning_today,
                travel_seconds=session.booking.travel_duration_seconds,
            ):
                _mark_sent(session.booking_day)
                sent += 1
        except Exception:
            logger.exception(
                "Departure reminder failed for booking %s on %s",
                session.booking.pk,
                session.on_date,
            )
    return sent

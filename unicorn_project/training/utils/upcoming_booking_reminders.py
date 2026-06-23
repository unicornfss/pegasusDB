import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.utils import timezone

from django.db.models import Q

from ..models import Booking, EmailNotification, Personnel, TelegramNotification
from .telegram_today import first_day_start_for_booking

logger = logging.getLogger(__name__)

_UPCOMING_TYPE_PREFIX = "upcoming_booking_"
_SCHEDULED_STATUSES = ("scheduled",)
_REMINDER_WINDOW = timedelta(minutes=6)


@dataclass(frozen=True)
class UpcomingReminderSession:
    booking: Booking
    personnel: Personnel
    offset_days: int
    first_date: datetime.date
    start_time: time


def upcoming_notification_type(offset_days: int) -> str:
    return f"{_UPCOMING_TYPE_PREFIX}{offset_days}"


def _already_sent(booking, offset_days: int) -> bool:
    ntype = upcoming_notification_type(offset_days)
    if TelegramNotification.objects.filter(
        booking=booking,
        notification_type=ntype,
        success=True,
    ).exists():
        return True
    return EmailNotification.objects.filter(
        booking=booking,
        notification_type=ntype,
        success=True,
    ).exists()


def _scheduled_bookings_for_personnel(personnel):
    return (
        Booking.objects.filter(
            instructor=personnel,
            status__in=_SCHEDULED_STATUSES,
        )
        .select_related("course_type", "business", "training_location", "instructor")
        .prefetch_related("days")
        .order_by("course_date", "start_time")
    )


def due_upcoming_reminders(now=None) -> list[UpcomingReminderSession]:
    now = now or timezone.localtime()
    today = now.date()
    due: list[UpcomingReminderSession] = []

    personnel_qs = Personnel.objects.filter(is_active=True).filter(
        Q(notify_upcoming_bookings_telegram=True) | Q(notify_upcoming_bookings_email=True)
    )

    for personnel in personnel_qs:
        offsets = personnel.upcoming_reminder_offsets()
        if not offsets:
            continue

        for booking in _scheduled_bookings_for_personnel(personnel):
            first_date, start_time = first_day_start_for_booking(booking)
            if not first_date or not start_time:
                continue
            if first_date <= today:
                continue

            for offset in offsets:
                reminder_date = first_date - timedelta(days=offset)
                if reminder_date != today:
                    continue
                if _already_sent(booking, offset):
                    continue

                reminder_dt = timezone.make_aware(datetime.combine(reminder_date, start_time))
                if reminder_dt <= now < reminder_dt + _REMINDER_WINDOW:
                    due.append(
                        UpcomingReminderSession(
                            booking=booking,
                            personnel=personnel,
                            offset_days=offset,
                            first_date=first_date,
                            start_time=start_time,
                        )
                    )
    return due


def send_due_upcoming_reminders(*, now=None) -> int:
    from .booking_notifications import notify_upcoming_booking_reminder

    sent = 0
    for session in due_upcoming_reminders(now=now):
        try:
            if notify_upcoming_booking_reminder(
                session.booking,
                offset_days=session.offset_days,
                first_date=session.first_date,
            ):
                sent += 1
        except Exception:
            logger.exception(
                "Upcoming booking reminder failed for booking %s (%s days)",
                session.booking.pk,
                session.offset_days,
            )
    return sent

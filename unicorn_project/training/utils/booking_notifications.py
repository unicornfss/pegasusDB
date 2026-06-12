from django.conf import settings

from ..models import TelegramNotification
from .booking_details import NOTIFICATION_HEADINGS, format_booking_telegram_message
from .telegram_client import send_telegram_message


NOTIFICATION_LABELS = {
    "new_booking": "new booking alert",
    "booking_changes": "booking update",
    "booking_cancellation": "cancellation alert",
    "booking_reminder": "reminder",
    "manual": "manual message",
    "resend": "booking details resend",
}


def should_notify_booking(booking) -> bool:
    """On production, skip dummy/practice businesses. On DEBUG dev, notify all."""
    if booking.is_dummy_business and not settings.DEBUG:
        return False
    return True


def personnel_wants_notification(personnel, notification_type: str) -> bool:
    if notification_type == "new_booking":
        return bool(personnel.notify_new_bookings_telegram)
    if notification_type in {"booking_changes", "booking_cancellation"}:
        return bool(personnel.notify_booking_changes_telegram)
    if notification_type == "booking_reminder":
        return bool(personnel.notify_reminders_telegram)
    return True


def notify_instructor_via_telegram(
    booking,
    notification_type: str,
    *,
    intro=None,
    changed_areas=None,
    force=False,
    sent_by=None,
):
    """
    Send a Telegram message to the booking instructor.
    Returns True when a message was sent successfully.
    force=True skips notification preference checks (manual send).
    """
    if not should_notify_booking(booking):
        return False

    if not (settings.TELEGRAM_BOT_TOKEN or "").strip():
        return False

    instructor = booking.instructor
    if not instructor or not (instructor.telegram_chat_id or "").strip():
        return False

    if not force and not personnel_wants_notification(instructor, notification_type):
        return False

    text = format_booking_telegram_message(
        booking,
        notification_type=notification_type,
        intro=intro,
        changed_areas=changed_areas,
    )
    message, error = send_telegram_message(instructor.telegram_chat_id, text)
    success = message is not None

    TelegramNotification.objects.create(
        booking=booking,
        personnel=instructor,
        notification_type=notification_type,
        message_id=str(message.message_id) if message else "",
        success=success,
        error_text=error or "",
    )
    return success


def notify_new_booking(booking):
    return notify_instructor_via_telegram(booking, "new_booking")


def notify_booking_changes(booking, *, intro=None, changed_areas=None):
    if not changed_areas:
        return False
    if intro is None:
        intro = "A booking assigned to you has been updated."
    return notify_instructor_via_telegram(
        booking,
        "booking_changes",
        intro=intro,
        changed_areas=changed_areas,
    )


def notify_booking_cancellation(booking, *, intro=None):
    from .booking_change_detection import CHANGE_CANCELLATION

    if intro is None:
        intro = "A booking assigned to you has been cancelled."
    return notify_instructor_via_telegram(
        booking,
        "booking_cancellation",
        intro=intro,
        changed_areas=[CHANGE_CANCELLATION],
    )


def notify_manual(booking, *, intro=None):
    if intro is None:
        intro = NOTIFICATION_HEADINGS.get("manual", "Booking details")
    return notify_instructor_via_telegram(booking, "manual", intro=intro, force=True)


def notify_resend(booking):
    return notify_instructor_via_telegram(booking, "resend", force=True)


def notify_booking_reminder(booking):
    return notify_instructor_via_telegram(booking, "booking_reminder")

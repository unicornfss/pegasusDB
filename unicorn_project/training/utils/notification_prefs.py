"""Instructor notification preferences (Telegram and email)."""


def should_notify_booking(booking) -> bool:
    """Practice/dummy bookings are notified with a clear not-real banner at the top."""
    return True


def should_notify_booking_detail_changes(booking) -> bool:
    """Suppress detail-change alerts while a course is in progress."""
    return getattr(booking, "status", None) != "in_progress"


def personnel_wants_notification(personnel, notification_type: str, *, channel: str = "telegram") -> bool:
    channel = (channel or "telegram").lower()
    suffix = "telegram" if channel == "telegram" else "email"

    if notification_type == "new_booking":
        return bool(getattr(personnel, f"notify_new_bookings_{suffix}", False))
    if notification_type in {"booking_changes", "booking_cancellation"}:
        return bool(getattr(personnel, f"notify_booking_changes_{suffix}", False))
    if notification_type in {"booking_reminder", "departure_reminder"}:
        return bool(getattr(personnel, f"notify_reminders_{suffix}", False))
    if notification_type.startswith("upcoming_booking_"):
        return bool(getattr(personnel, f"notify_upcoming_bookings_{suffix}", False))
    return True

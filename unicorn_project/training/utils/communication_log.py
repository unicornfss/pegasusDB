import re
from datetime import datetime, timezone as dt_timezone

from .booking_notifications import NOTIFICATION_LABELS

_LOG_LINE_RE = re.compile(r"^\[.+?\]\s+(Telegram|Email)\s+", re.IGNORECASE)


def user_editable_booking_notes(booking) -> str:
    """Course notes without auto-generated Telegram/Email log lines."""
    lines = (booking.booking_notes or "").splitlines()
    kept = [line for line in lines if line.strip() and not _LOG_LINE_RE.match(line.strip())]
    return "\n".join(kept).strip()


def _notification_label(notification_type: str) -> str:
    if notification_type in NOTIFICATION_LABELS:
        return NOTIFICATION_LABELS[notification_type]
    if notification_type.startswith("upcoming_booking_"):
        offset = notification_type.removeprefix("upcoming_booking_")
        day_word = "day" if offset == "1" else "days"
        return f"upcoming booking reminder ({offset} {day_word} before)"
    return notification_type.replace("_", " ")


def _recipient_name(personnel) -> str:
    if not personnel:
        return ""
    return (personnel.name or personnel.email or "instructor").strip()


def _format_notification_message(
    *,
    channel: str,
    notification_type: str,
    personnel,
    success: bool,
    error_text: str = "",
) -> str:
    label = _notification_label(notification_type)
    recipient = _recipient_name(personnel)

    if success:
        message = f"{label} sent"
        if channel == "Email":
            message += " with course pack PDF"
        if recipient:
            message += f" to {recipient}"
        return message + "."

    message = f"{label} failed"
    if recipient:
        message += f" for {recipient}"
    message += "."
    if error_text:
        message += f" ({error_text})"
    return message


def _entries_from_notifications(queryset, *, channel: str) -> list[dict]:
    entries = []
    for item in queryset:
        entries.append(
            {
                "sent_at": item.sent_at,
                "channel": channel,
                "message": _format_notification_message(
                    channel=channel,
                    notification_type=item.notification_type,
                    personnel=item.personnel,
                    success=item.success,
                    error_text=item.error_text or "",
                ),
                "success": item.success,
            }
        )
    return entries


def communication_log_entries(booking):
    """Read-only notification history for a booking (newest first)."""
    entries = []

    entries.extend(
        _entries_from_notifications(
            booking.telegram_notifications.select_related("personnel").all(),
            channel="Telegram",
        )
    )
    entries.extend(
        _entries_from_notifications(
            booking.email_notifications.select_related("personnel").all(),
            channel="Email",
        )
    )

    seen_messages = {e["message"] for e in entries if e.get("sent_at")}
    for line in (booking.booking_notes or "").splitlines():
        stripped = line.strip()
        if not stripped or not _LOG_LINE_RE.match(stripped):
            continue
        if stripped in seen_messages:
            continue
        entries.append(
            {
                "sent_at": None,
                "channel": "Telegram" if "telegram" in stripped.lower() else "Email",
                "message": stripped,
                "success": "failed" not in stripped.lower(),
                "legacy": True,
            }
        )

    entries.sort(
        key=lambda entry: entry["sent_at"] or datetime.min.replace(tzinfo=dt_timezone.utc),
        reverse=True,
    )
    return entries

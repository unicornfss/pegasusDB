import re
from datetime import datetime, timezone as dt_timezone

from .booking_notifications import NOTIFICATION_LABELS

_LOG_LINE_RE = re.compile(r"^\[.+?\]\s+(Telegram|Email)\s+", re.IGNORECASE)


def user_editable_booking_notes(booking) -> str:
    """Course notes without auto-generated Telegram/Email log lines."""
    lines = (booking.booking_notes or "").splitlines()
    kept = [line for line in lines if line.strip() and not _LOG_LINE_RE.match(line.strip())]
    return "\n".join(kept).strip()


def communication_log_entries(booking):
    """Read-only notification history for a booking (newest first)."""
    entries = []

    notifications = booking.telegram_notifications.select_related("personnel").all()
    for item in notifications:
        label = NOTIFICATION_LABELS.get(item.notification_type, item.notification_type)
        recipient = ""
        if item.personnel:
            recipient = item.personnel.name or item.personnel.email or "instructor"
        if item.success:
            message = f"Telegram {label} sent to {recipient}." if recipient else f"Telegram {label} sent."
        else:
            message = f"Telegram {label} failed"
            if recipient:
                message += f" for {recipient}"
            message += "."
            if item.error_text:
                message += f" ({item.error_text})"
        entries.append(
            {
                "sent_at": item.sent_at,
                "channel": "Telegram",
                "message": message,
                "success": item.success,
            }
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

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..models import Personnel

SETTINGS_CALLBACK_PREFIX = "st:"

TELEGRAM_SETTING_KEYS = {
    "n": ("notify_new_bookings_telegram", "New bookings"),
    "c": ("notify_booking_changes_telegram", "Booking updates"),
    "u": ("notify_upcoming_bookings_telegram", "Upcoming bookings"),
    "r": ("notify_reminders_telegram", "Departure reminders"),
}


def _setting_status(on: bool) -> str:
    return "ON ✅" if on else "OFF"


def _upcoming_days_label(personnel) -> str:
    offsets = personnel.upcoming_reminder_offsets()
    if not offsets:
        return "no days chosen"
    return ", ".join(f"{n}d" for n in offsets)


def format_settings_message(personnel):
    lines = [
        "<b>Telegram notification settings</b>",
        "",
        "Tap a row to turn alerts on or off.",
        "Set upcoming reminder days on your Pegasus profile page.",
        "",
    ]
    for key, (field, label) in TELEGRAM_SETTING_KEYS.items():
        status = _setting_status(getattr(personnel, field))
        line = f"• {label}: <b>{status}</b>"
        if key == "u" and getattr(personnel, field):
            line += f" ({_upcoming_days_label(personnel)})"
        lines.append(line)
    return "\n".join(lines)


def settings_keyboard(personnel):
    rows = []
    for key, (field, label) in TELEGRAM_SETTING_KEYS.items():
        status = _setting_status(getattr(personnel, field))
        rows.append([
            InlineKeyboardButton(f"{label}: {status}", callback_data=f"{SETTINGS_CALLBACK_PREFIX}{key}")
        ])
    return InlineKeyboardMarkup(rows)


def toggle_personnel_setting(personnel, setting_key: str):
    field_name, _label = TELEGRAM_SETTING_KEYS[setting_key]
    new_value = not getattr(personnel, field_name)
    Personnel.objects.filter(pk=personnel.pk).update(**{field_name: new_value})
    personnel.refresh_from_db()
    return personnel

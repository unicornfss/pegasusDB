from django.db.models import Q
from django.utils import timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..models import Booking
from .booking_details import (
    _list_disclaimer_lines,
    format_booking_details_lookup_message,
    google_maps_url_for_booking,
    prepend_notification_disclaimer,
)

BOOKING_DETAIL_CALLBACK_PREFIX = "bd:"


def personnel_for_chat_id(chat_id: str):
    from ..models import Personnel

    chat_id = (chat_id or "").strip()
    if not chat_id:
        return None
    return Personnel.objects.filter(telegram_chat_id=chat_id, is_active=True).first()


def upcoming_bookings_for_personnel(personnel, *, limit=10):
    today = timezone.localdate()
    return (
        Booking.objects.filter(instructor=personnel)
        .filter(
            Q(status="scheduled") | Q(status="in_progress") | Q(status="awaiting_closure")
        )
        .filter(course_date__gte=today)
        .select_related("course_type", "business", "training_location")
        .prefetch_related("days")
        .order_by("course_date", "start_time")[:limit]
    )


def next_upcoming_booking_for_personnel(personnel):
    return upcoming_bookings_for_personnel(personnel, limit=1).first()


def booking_for_personnel_by_id(personnel, booking_id):
    if booking_id is None or booking_id == "":
        return None
    return (
        Booking.objects.filter(pk=booking_id, instructor=personnel)
        .select_related("course_type", "business", "training_location")
        .prefetch_related("days")
        .first()
    )


def format_bookings_list(bookings):
    if not bookings:
        return "You have no upcoming bookings."

    lines = list(_list_disclaimer_lines(bookings))
    lines.extend(["<b>Your upcoming bookings</b>", ""])
    for i, booking in enumerate(bookings, start=1):
        ref = booking.course_reference or "—"
        course = getattr(booking.course_type, "name", "") or "Course"
        date_str = booking.course_date.strftime("%a %d %b %Y") if booking.course_date else "—"
        loc = getattr(booking.training_location, "name", "") or ""
        dummy = " (practice)" if booking.is_dummy_business else ""
        lines.append(f"{i}. <b>{ref}</b>{dummy}")
        lines.append(f"   {course} · {date_str}")
        if loc:
            lines.append(f"   {loc}")
        lines.append("")
    lines.append("")
    lines.append("👇 <b>Select a course below for full details.</b>")
    lines.append("<i>Or reply with its list number (e.g. 1).</i>")
    lines.append("")
    lines.append("Use /directions for your next booking location.")
    return "\n".join(lines).strip()


def _booking_button_label(booking):
    date_str = booking.course_date.strftime("%a %d %b %Y") if booking.course_date else "—"
    course = getattr(booking.course_type, "name", "") or "Course"
    label = f"{date_str} · {course}"
    if len(label) > 64:
        label = f"{date_str} · {course[: max(0, 64 - len(date_str) - 3)]}".strip(" ·")
        if len(label) > 64:
            label = label[:61] + "..."
    return label


def bookings_list_keyboard(bookings):
    rows = []
    for booking in bookings:
        rows.append([
            InlineKeyboardButton(
                _booking_button_label(booking),
                callback_data=f"{BOOKING_DETAIL_CALLBACK_PREFIX}{booking.pk}",
            )
        ])
    return InlineKeyboardMarkup(rows)


def format_booking_details_message(booking):
    return format_booking_details_lookup_message(booking)


def format_directions_message(booking):
    if not booking:
        return "You have no upcoming bookings."

    loc = booking.training_location
    course = getattr(booking.course_type, "name", "") or "Course"
    date_str = booking.course_date.strftime("%a %d %b %Y") if booking.course_date else "—"

    lines = [
        "<b>Next booking location</b>",
        "",
        f"{date_str} · {course}",
        "",
    ]

    if not loc:
        lines.append("No location is recorded for this booking.")
    else:
        for part in (loc.name, loc.property_name, loc.address_line, loc.town, loc.postcode):
            if part:
                lines.append(part)

    maps_url = google_maps_url_for_booking(booking)
    if maps_url:
        lines.append("")
        lines.append(f'<a href="{maps_url}">Open in Google Maps</a>')
    elif not loc:
        return prepend_notification_disclaimer("\n".join(lines).strip(), booking)

    body = "\n".join(lines).strip()
    return prepend_notification_disclaimer(body, booking)

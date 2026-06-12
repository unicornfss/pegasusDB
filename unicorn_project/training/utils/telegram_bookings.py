from django.db.models import Q
from django.utils import timezone

from ..models import Booking


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
        .order_by("course_date", "start_time")[:limit]
    )


def booking_for_personnel_by_reference(personnel, reference: str):
    reference = (reference or "").strip()
    if not reference:
        return None
    return (
        Booking.objects.filter(instructor=personnel, course_reference__iexact=reference)
        .select_related("course_type", "business", "training_location")
        .first()
    )


def format_bookings_list(bookings):
    if not bookings:
        return "You have no upcoming bookings."

    lines = ["<b>Your upcoming bookings</b>", ""]
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
    lines.append("Use /directions REF to get directions for a booking reference.")
    return "\n".join(lines).strip()


from .booking_details import google_maps_url_for_booking


def format_directions_message(booking):
    loc = booking.training_location
    if not loc:
        return "No location is recorded for this booking."

    lines = [
        f"<b>Directions — {booking.course_reference or 'booking'}</b>",
        "",
        loc.name or "",
        loc.property_name or "",
        loc.address_line or "",
        loc.town or "",
        loc.postcode or "",
    ]
    maps_url = google_maps_url_for_booking(booking)
    if maps_url:
        lines.append("")
        lines.append(f'<a href="{maps_url}">Open in Google Maps</a>')
    return "\n".join(line for line in lines if line is not None).strip()

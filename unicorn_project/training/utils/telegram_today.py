from html import escape
from io import BytesIO
from urllib.parse import urlencode

from django.conf import settings
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile

from ..models import Booking
from .booking_details import _location_lines, google_maps_url_for_booking, prepend_notification_disclaimer
from .register_links import qr_png_bytes

BOOKING_REGISTER_CALLBACK_PREFIX = "br:"
BOOKING_FEEDBACK_CALLBACK_PREFIX = "bf:"

_ACTIVE_STATUSES = Q(status="scheduled") | Q(status="in_progress") | Q(status="awaiting_closure")


def pegasus_site_url() -> str:
    return (getattr(settings, "SITE_URL", "") or "").rstrip("/")


def bookings_on_date_for_personnel(personnel, on_date=None):
    on_date = on_date or timezone.localdate()
    return (
        Booking.objects.filter(instructor=personnel)
        .filter(_ACTIVE_STATUSES)
        .filter(Q(course_date=on_date) | Q(days__date=on_date))
        .distinct()
        .select_related("course_type", "business", "training_location", "instructor")
        .prefetch_related("days")
        .order_by("start_time", "course_date")
    )


def first_day_start_for_booking(booking):
    day = booking.days.order_by("date").first()
    if day:
        return day.date, (day.start_time or booking.start_time)
    return booking.course_date, booking.start_time


def _booking_times_on_date(booking, on_date):
    day = booking.days.filter(date=on_date).first()
    if day and day.start_time:
        start = day.start_time.strftime("%H:%M")
        if day.end_time:
            return f"{start}–{day.end_time.strftime('%H:%M')}"
        return start
    if booking.course_date == on_date and booking.start_time:
        return booking.start_time.strftime("%H:%M")
    return ""


def _today_booking_button_label(booking, on_date):
    course = getattr(booking.course_type, "name", "") or "Course"
    times = _booking_times_on_date(booking, on_date)
    label = f"{course} · {times}" if times else course
    if len(label) > 64:
        label = course[:61] + "..." if len(course) > 64 else course
    return label


def today_bookings_keyboard(bookings, *, on_date, callback_prefix):
    rows = []
    for booking in bookings:
        rows.append([
            InlineKeyboardButton(
                _today_booking_button_label(booking, on_date),
                callback_data=f"{callback_prefix}{booking.pk}",
            )
        ])
    return InlineKeyboardMarkup(rows)


def format_today_message(bookings, on_date=None, *, section_title="Today"):
    on_date = on_date or timezone.localdate()
    date_label = on_date.strftime("%a %d %b %Y")

    if not bookings:
        if section_title:
            return f"You have no courses scheduled for <b>{escape(date_label)}</b>."
        return "You have no upcoming course details to show."

    lines = []
    if section_title:
        lines.extend([f"<b>{escape(section_title)} — {escape(date_label)}</b>", ""])

    for booking in bookings:
        ref = booking.course_reference or "—"
        course = getattr(booking.course_type, "name", "") or "Course"
        business = getattr(booking.business, "name", "") or ""
        times = _booking_times_on_date(booking, on_date)
        dummy = " (practice)" if booking.is_dummy_business else ""

        lines.append(f"<b>{escape(course)}</b>{dummy}")
        lines.append(f"Ref: {escape(ref)}")
        if times:
            lines.append(f"Time: {escape(times)}")
        if business:
            lines.append(f"Business: {escape(business)}")

        loc = booking.training_location
        if loc:
            loc_bits = _location_lines(loc)
            if loc_bits:
                lines.append(f"Location: {escape(', '.join(loc_bits))}")

        contact_bits = [b for b in (booking.contact_name, booking.telephone) if b]
        if contact_bits:
            lines.append(f"Contact: {escape(' · '.join(contact_bits))}")

        notes = (booking.booking_notes or "").strip()
        if notes:
            short = notes if len(notes) <= 240 else notes[:237] + "…"
            lines.append(f"Notes: {escape(short)}")

        maps_url = google_maps_url_for_booking(booking)
        if maps_url:
            lines.append(f'<a href="{maps_url}">Open in Google Maps</a>')

        lines.append("")

    lines.append("/registration · /feedback · /directions")
    body = "\n".join(lines).strip()
    if any(getattr(b, "is_dummy_business", False) for b in bookings) or settings.DEBUG:
        return prepend_notification_disclaimer(body, bookings[0])
    return body


def format_morning_today_reminder_message(booking, on_date):
    """Course-day summary at a fixed morning time (no travel-time header)."""
    return format_today_message([booking], on_date)


def format_departure_reminder_message(booking, on_date, *, travel_seconds, buffer_minutes):
    travel_mins = max(1, round(travel_seconds / 60))
    start_label = _booking_times_on_date(booking, on_date) or "—"
    header = (
        f"🚗 <b>Time to get ready</b>\n\n"
        f"You should leave in about <b>{buffer_minutes} minutes</b> "
        f"(~{travel_mins}-minute drive to the venue).\n"
        f"Course start: <b>{escape(start_label)}</b>\n"
    )
    body = format_today_message([booking], on_date)
    return f"{header}\n{body}"


def format_upcoming_booking_reminder_message(booking, *, offset_days, first_date):
    day_word = "day" if offset_days == 1 else "days"
    start_label = _booking_times_on_date(booking, first_date) or "—"
    header = (
        f"📅 <b>Upcoming course in {offset_days} {day_word}</b>\n\n"
        f"Course starts: <b>{escape(first_date.strftime('%a %d %b %Y'))}</b> "
        f"at <b>{escape(start_label)}</b>\n"
    )
    body = format_today_message([booking], first_date, section_title="")
    return f"{header}\n{body}"


def booking_register_form_url(booking, on_date=None):
    on_date = on_date or timezone.localdate()
    site = pegasus_site_url()
    code = getattr(booking.course_type, "code", "") or ""
    if not site or not code:
        return ""

    params = {
        "ct": code,
        "date": on_date.isoformat(),
        "instructor": str(booking.instructor_id),
    }
    day = booking.days.filter(date=on_date).first()
    if day and day.day_code:
        params["day"] = day.day_code
    return f"{site}{reverse('public_delegate_register')}?{urlencode(params)}"


def booking_feedback_form_url(booking, on_date=None):
    on_date = on_date or timezone.localdate()
    site = pegasus_site_url()
    code = getattr(booking.course_type, "code", "") or ""
    if not site or not code:
        return ""

    params = {
        "course": code,
        "date": on_date.isoformat(),
        "instructor": str(booking.instructor_id),
    }
    return f"{site}{reverse('public_feedback_form')}?{urlencode(params)}"


def _form_caption(*, title, booking, on_date, url):
    course = getattr(booking.course_type, "name", "") or "Course"
    date_label = on_date.strftime("%a %d %b %Y")
    lines = [
        f"<b>{escape(title)}</b>",
        "",
        f"{escape(course)} · {escape(date_label)}",
        "",
        f'<a href="{escape(url)}">Open form</a>',
    ]
    body = "\n".join(lines)
    return prepend_notification_disclaimer(body, booking)


def registration_qr_photo_and_caption(booking, on_date=None):
    on_date = on_date or timezone.localdate()
    url = booking_register_form_url(booking, on_date)
    if not url:
        return None, "Could not build the registration link for this course."
    caption = _form_caption(
        title="Delegate registration",
        booking=booking,
        on_date=on_date,
        url=url,
    )
    return qr_png_bytes(url), caption


def feedback_qr_photo_and_caption(booking, on_date=None):
    on_date = on_date or timezone.localdate()
    url = booking_feedback_form_url(booking, on_date)
    if not url:
        return None, "Could not build the feedback link for this course."
    caption = _form_caption(
        title="Course feedback",
        booking=booking,
        on_date=on_date,
        url=url,
    )
    return qr_png_bytes(url), caption


def telegram_qr_input_file(png_bytes, filename="qr.png"):
    return InputFile(BytesIO(png_bytes), filename=filename)

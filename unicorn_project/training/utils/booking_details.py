from html import escape
from urllib.parse import quote

from django.conf import settings
from django.urls import reverse


from .booking_change_detection import (
    CHANGE_CANCELLATION,
    CHANGE_COURSE_NOTES,
    CHANGE_DATES_TIMES,
    CHANGE_INSTRUCTOR_FEE,
    CHANGE_REINSTATEMENT,
    format_changed_areas_label,
)
from .site_url import public_site_url

NOTIFICATION_HEADINGS = {
    "new_booking": "New booking assigned",
    "booking_changes": "Booking updated",
    "booking_cancellation": "Booking cancelled",
    "booking_reminder": "Upcoming booking reminder",
    "manual": "Booking details",
    "resend": "Booking details",
}

GREETING_TYPES = frozenset({"new_booking", "resend", "booking_reminder"})


def notification_disclaimer_lines(booking, *, html=True):
    """
    Banner lines for the top of booking notifications (Telegram HTML or plain email).
    Shown on dev (DEBUG) for every message, and on practice/dummy bookings in production.
    """
    lines = []
    if settings.DEBUG:
        if html:
            lines.extend([
                "⚠️ <b>DEV / TEST — NOT A REAL BOOKING</b>",
                "<i>Sent from a development environment. Do not treat this as a live course.</i>",
            ])
        else:
            lines.extend([
                "DEV / TEST — NOT A REAL BOOKING",
                "Sent from a development environment. Do not treat this as a live course.",
            ])
    elif getattr(booking, "is_dummy_business", False):
        if html:
            lines.extend([
                "⚠️ <b>PRACTICE BOOKING — NOT A REAL BOOKING</b>",
                "<i>Familiarisation / practice only. This is not a live customer booking.</i>",
            ])
        else:
            lines.extend([
                "PRACTICE BOOKING — NOT A REAL BOOKING",
                "Familiarisation / practice only. This is not a live customer booking.",
            ])
    if lines:
        lines.append("")
    return lines


def prepend_notification_disclaimer(body, booking, *, html=True):
    banner = notification_disclaimer_lines(booking, html=html)
    if not banner:
        return body
    return "\n".join(banner + [body])


def _list_disclaimer_lines(bookings, *, html=True):
    """Disclaimer for /bookings list when dev or any practice booking is included."""
    if settings.DEBUG:
        if html:
            return [
                "⚠️ <b>DEV / TEST — NOT REAL BOOKINGS</b>",
                "<i>Development environment — courses listed may be for testing only.</i>",
                "",
            ]
        return [
            "DEV / TEST — NOT REAL BOOKINGS",
            "Development environment — courses listed may be for testing only.",
            "",
        ]
    if any(getattr(b, "is_dummy_business", False) for b in bookings):
        if html:
            return [
                "⚠️ <b>PRACTICE BOOKINGS BELOW — NOT REAL BOOKINGS</b>",
                "<i>Items marked (practice) are familiarisation bookings only.</i>",
                "",
            ]
        return [
            "PRACTICE BOOKINGS BELOW — NOT REAL BOOKINGS",
            "Items marked (practice) are familiarisation bookings only.",
            "",
        ]
    return []


def _format_time(value):
    if not value:
        return ""
    return value.strftime("%H:%M")


def _format_money(value):
    if value is None:
        return "—"
    return f"£{value:.2f}"


def _location_lines(location):
    if not location:
        return []
    parts = [
        location.name or "",
        location.property_name or "",
        location.address_line or "",
        location.town or "",
        location.postcode or "",
    ]
    return [p for p in parts if p.strip()]


def _instructor_first_name(booking):
    instructor = booking.instructor
    if not instructor:
        return "there"

    user = getattr(instructor, "user", None)
    if user and (user.first_name or "").strip():
        return user.first_name.strip()

    name = (instructor.name or "").strip()
    if name:
        return name.split()[0]

    email = (instructor.email or "").strip()
    if email and "@" in email:
        return email.split("@")[0]

    return "there"


def _greeting_line(booking, notification_type):
    first_name = escape(_instructor_first_name(booking))
    if notification_type == "booking_reminder":
        return f"Dear {first_name}, this is a reminder for the course you have coming up."
    if notification_type in {"new_booking", "resend"}:
        return f"Dear {first_name}, a course has been booked for you, the details are below:"
    return ""


def google_maps_url_for_booking(booking):
    lat = booking.effective_precise_lat()
    lng = booking.effective_precise_lng()

    if lat is not None and lng is not None:
        return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"

    loc = booking.training_location
    if not loc:
        return None
    address = ", ".join(_location_lines(loc))
    if not address:
        return None
    return f"https://www.google.com/maps/search/?api=1&query={quote(address)}"


def _format_course_day_lines(booking):
    days = list(booking.days.all().order_by("date", "start_time"))
    if days:
        lines = []
        for index, day in enumerate(days, start=1):
            date_str = day.date.strftime("%a %d %b %Y")
            start = _format_time(day.start_time)
            end = _format_time(day.end_time)
            if start and end:
                when = f"{date_str}, {start}–{end}"
            elif start:
                when = f"{date_str}, {start}"
            else:
                when = date_str
            lines.append(f"Day {index}: {when}")
        return lines

    if booking.course_date:
        date_str = booking.course_date.strftime("%a %d %b %Y")
        start = _format_time(booking.start_time)
        when = f"{date_str} {start}".strip() if start else date_str
        return [when]
    return []


def format_booking_course_day_lines(booking):
    """Human-readable date/time lines for each course day."""
    return _format_course_day_lines(booking)


def format_booking_dates_compact(booking):
    """Short date text for lists: one day, or a first–last range when multi-day."""
    day_lines = _format_course_day_lines(booking)
    if not day_lines:
        return "—"
    if len(day_lines) == 1:
        line = day_lines[0]
        if line.startswith("Day 1: "):
            return line[7:]
        return line

    days = list(booking.days.all().order_by("date"))
    if len(days) >= 2:
        first = days[0].date.strftime("%a %d %b %Y")
        last = days[-1].date.strftime("%a %d %b %Y")
        return f"{first} – {last}"
    return day_lines[0]


def _format_booking_details_block(booking, *, highlight=None):
    highlight = highlight or frozenset()
    lines = []

    ref = booking.course_reference or "—"
    lines.append(f"🔖 <b>Reference:</b> {escape(ref)}")

    course_name = getattr(booking.course_type, "name", "") or "Course"
    lines.append(f"📚 <b>Course type:</b> {escape(course_name)}")

    business_name = getattr(booking.business, "name", "") or ""
    if business_name:
        lines.append(f"🏢 <b>Business:</b> {escape(business_name)}")

    loc = booking.training_location
    if loc:
        loc_label = ", ".join(_location_lines(loc)) or (loc.name or "")
        if loc_label:
            lines.append(f"📍 <b>Location:</b> {escape(loc_label)}")

    day_lines = _format_course_day_lines(booking)
    if day_lines:
        mark = "✏️ " if "dates" in highlight else ""
        lines.append(f"{mark}📅 <b>Course date(s):</b>")
        for line in day_lines:
            lines.append(f"   {escape(line)}")

    notes = (booking.booking_notes or "").strip()
    if notes or "notes" in highlight:
        mark = "✏️ " if "notes" in highlight else ""
        lines.append(f"{mark}📝 <b>Course notes:</b> {escape(notes or '—')}")

    mark = "✏️ " if "instructor_fee" in highlight else ""
    lines.append(f"{mark}💷 <b>Instructor fee:</b> {escape(_format_money(booking.instructor_fee))}")

    status = booking.get_status_display() if hasattr(booking, "get_status_display") else booking.status
    if status:
        mark = "✏️ " if "status" in highlight else ""
        lines.append(f"{mark}ℹ️ <b>Status:</b> {escape(str(status))}")

    if booking.status == "cancelled" and booking.cancel_reason:
        mark = "✏️ " if "status" in highlight else ""
        lines.append(f"{mark}❌ <b>Reason:</b> {escape(booking.cancel_reason)}")

    maps_url = google_maps_url_for_booking(booking)
    if maps_url:
        lines.append(f'🗺️ <a href="{maps_url}">Open destination in Google Maps</a>')

    plus_code = booking.effective_plus_code()
    if plus_code:
        lines.append(f'📍 <a href="{booking.plus_code_url()}">Plus code: {escape(plus_code)}</a>')

    site = public_site_url()
    if site and booking.pk:
        path = reverse("instructor_booking_detail", args=[booking.pk])
        lines.append(f'🔗 <a href="{site}{path}">Open booking in Pegasus</a>')

    return lines


def _highlights_for_changed_areas(changed_areas):
    highlights = set()
    if not changed_areas:
        return frozenset()
    if CHANGE_DATES_TIMES in changed_areas:
        highlights.add("dates")
    if CHANGE_COURSE_NOTES in changed_areas:
        highlights.add("notes")
    if CHANGE_INSTRUCTOR_FEE in changed_areas:
        highlights.add("instructor_fee")
    if CHANGE_CANCELLATION in changed_areas or CHANGE_REINSTATEMENT in changed_areas:
        highlights.add("status")
    return frozenset(highlights)


def _format_changed_banner(changed_areas):
    label = format_changed_areas_label(changed_areas or [])
    if not label:
        return None
    return f"🔔 <b>Changed:</b> {escape(label)}"


def _format_notified_change_message(booking, *, heading_key, intro, changed_areas):
    heading = NOTIFICATION_HEADINGS.get(heading_key, "Booking notification")
    first_name = escape(_instructor_first_name(booking))
    lines = [f"<b>{escape(heading)}</b>"]

    banner = _format_changed_banner(changed_areas)
    if banner:
        lines.extend(["", banner])

    if intro:
        lines.extend(["", escape(intro)])

    if heading_key == "booking_changes":
        lines.extend(["", f"Dear {first_name}, here are the updated booking details. Items marked ✏️ have changed:"])
    elif heading_key == "booking_cancellation":
        lines.extend(["", f"Dear {first_name}, please review the cancelled booking below:"])

    lines.append("")
    lines.extend(
        _format_booking_details_block(
            booking,
            highlight=_highlights_for_changed_areas(changed_areas),
        )
    )
    return "\n".join(lines)


def format_booking_resend_telegram_message(booking):
    return format_booking_telegram_message(booking, notification_type="resend")


def format_booking_details_lookup_message(booking):
    """Full booking block for /bookings drill-down (no notification greeting)."""
    ref = booking.course_reference or "—"
    lines = [f"<b>Booking details — {escape(ref)}</b>", ""]
    lines.extend(_format_booking_details_block(booking))
    return prepend_notification_disclaimer("\n".join(lines), booking)


def format_booking_telegram_message(booking, *, notification_type, intro=None, changed_areas=None):
    if notification_type in GREETING_TYPES:
        lines = [_greeting_line(booking, notification_type), ""]
        lines.extend(_format_booking_details_block(booking))
        return prepend_notification_disclaimer("\n".join(lines), booking)

    if notification_type == "booking_changes" and changed_areas:
        if intro is None:
            intro = "A booking assigned to you has been updated."
        body = _format_notified_change_message(
            booking,
            heading_key="booking_changes",
            intro=intro,
            changed_areas=changed_areas,
        )
        return prepend_notification_disclaimer(body, booking)

    if notification_type == "booking_cancellation":
        if intro is None:
            intro = "A booking assigned to you has been cancelled."
        body = _format_notified_change_message(
            booking,
            heading_key="booking_cancellation",
            intro=intro,
            changed_areas=changed_areas or [CHANGE_CANCELLATION],
        )
        return prepend_notification_disclaimer(body, booking)

    heading = NOTIFICATION_HEADINGS.get(notification_type, "Booking notification")
    lines = [f"<b>{escape(heading)}</b>"]
    if intro:
        lines.append(escape(intro))

    ref = booking.course_reference or "—"
    lines.append(f"\n🔖 <b>Ref:</b> {escape(ref)}")

    course_name = getattr(booking.course_type, "name", "") or "Course"
    lines.append(f"📚 <b>Course:</b> {escape(course_name)}")

    business_name = getattr(booking.business, "name", "") or ""
    if business_name:
        lines.append(f"🏢 <b>Business:</b> {escape(business_name)}")

    if booking.course_date:
        date_str = booking.course_date.strftime("%a %d %b %Y")
        time_str = _format_time(booking.start_time)
        when = f"{date_str} {time_str}".strip()
        lines.append(f"📅 <b>Date:</b> {escape(when)}")

    loc_lines = _location_lines(booking.training_location)
    if loc_lines:
        lines.append(f"📍 <b>Location:</b> {escape(', '.join(loc_lines))}")

    if booking.contact_name or booking.telephone:
        contact_bits = [b for b in [booking.contact_name, booking.telephone] if b]
        lines.append(f"📞 <b>Contact:</b> {escape(' · '.join(contact_bits))}")

    status = booking.get_status_display() if hasattr(booking, "get_status_display") else booking.status
    if status:
        lines.append(f"ℹ️ <b>Status:</b> {escape(str(status))}")

    if booking.status == "cancelled" and booking.cancel_reason:
        lines.append(f"❌ <b>Reason:</b> {escape(booking.cancel_reason)}")

    maps_url = google_maps_url_for_booking(booking)
    if maps_url:
        lines.append(f'\n🗺️ <a href="{maps_url}">Open destination in Google Maps</a>')

    plus_code = booking.effective_plus_code()
    if plus_code:
        lines.append(f'📍 <a href="{booking.plus_code_url()}">Plus code: {escape(plus_code)}</a>')

    site = public_site_url()
    if site and booking.pk:
        path = reverse("instructor_booking_detail", args=[booking.pk])
        lines.append(f'\n🔗 <a href="{site}{path}">Open booking in Pegasus</a>')

    return prepend_notification_disclaimer("\n".join(lines), booking)

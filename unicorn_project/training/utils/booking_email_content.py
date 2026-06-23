"""HTML/plain email bodies for instructor booking notifications."""

from __future__ import annotations

from html import escape

from django.template.loader import render_to_string
from django.urls import reverse

from .booking_change_detection import format_changed_areas_label
from .booking_details import (
    NOTIFICATION_HEADINGS,
    _format_course_day_lines,
    _format_money,
    _instructor_first_name,
    _location_lines,
    google_maps_url_for_booking,
    notification_disclaimer_lines,
    prepend_notification_disclaimer,
)
from .booking_notification_pdf import absolute_url, build_booking_pack_context
from .telegram_today import (
    format_departure_reminder_message,
    format_morning_today_reminder_message,
    format_upcoming_booking_reminder_message,
)


def _strip_telegram_html(text: str) -> str:
    """Rough plain-text version of Telegram HTML messages."""
    import re

    text = re.sub(r"<a[^>]*href=\"([^\"]+)\"[^>]*>[^<]*</a>", r"\1", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</?b>", "", text, flags=re.I)
    text = re.sub(r"</?i>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def booking_email_subject(notification_type: str, booking) -> str:
    ref = booking.course_reference or "booking"
    headings = {
        **NOTIFICATION_HEADINGS,
        "departure_reminder": "Departure reminder",
        "booking_cancellation": "Booking cancelled",
    }
    if notification_type.startswith("upcoming_booking_"):
        label = "Upcoming course reminder"
    else:
        label = headings.get(notification_type, "Booking notification")
    return f"{label} — {ref}"


def _email_intro_lines(booking, notification_type, *, intro=None, changed_areas=None) -> list[str]:
    first = _instructor_first_name(booking)
    lines: list[str] = []

    if notification_type == "new_booking":
        lines.append(f"Dear {first}, a course has been booked for you. Full details are in the attached PDF.")
    elif notification_type == "resend":
        lines.append(f"Dear {first}, here are your booking details again (also attached as a PDF).")
    elif notification_type == "manual":
        lines.append(intro or "Booking details are below and attached as a PDF.")
    elif notification_type == "booking_reminder":
        lines.append(f"Dear {first}, this is a reminder for your upcoming course.")
    elif notification_type == "booking_changes":
        label = format_changed_areas_label(changed_areas or [])
        lines.append(intro or "A booking assigned to you has been updated.")
        if label:
            lines.append(f"Changed: {label}")
        lines.append("Updated details are in the attached PDF.")
    elif notification_type == "booking_cancellation":
        lines.append(intro or "A booking assigned to you has been cancelled.")
    elif notification_type == "departure_reminder":
        lines.append("Time to get ready — your course is today. See the attached PDF for venue, QR codes and contacts.")
    elif notification_type.startswith("upcoming_booking_"):
        lines.append("You have an upcoming course. Venue, contacts and QR codes are in the attached PDF.")

    return lines


def format_booking_email_plain(
    booking,
    notification_type: str,
    *,
    intro=None,
    changed_areas=None,
    on_date=None,
    offset_days=None,
    first_date=None,
    travel_seconds=None,
    buffer_minutes=None,
    morning_today=False,
) -> str:
    if notification_type == "departure_reminder" and on_date:
        if morning_today:
            body = format_morning_today_reminder_message(booking, on_date)
        else:
            from django.conf import settings

            body = format_departure_reminder_message(
                booking,
                on_date,
                travel_seconds=int(travel_seconds or 0),
                buffer_minutes=int(buffer_minutes or getattr(settings, "DEPARTURE_REMINDER_BUFFER_MINUTES", 30)),
            )
        return _strip_telegram_html(body)

    if notification_type.startswith("upcoming_booking_") and first_date is not None and offset_days is not None:
        body = format_upcoming_booking_reminder_message(
            booking,
            offset_days=offset_days,
            first_date=first_date,
        )
        return _strip_telegram_html(body)

    lines = list(_email_intro_lines(booking, notification_type, intro=intro, changed_areas=changed_areas))
    lines.append("")
    lines.extend(notification_disclaimer_lines(booking, html=False))

    ref = booking.course_reference or "—"
    lines.append(f"Reference: {ref}")
    lines.append(f"Course: {getattr(booking.course_type, 'name', '') or 'Course'}")
    business = getattr(booking.business, "name", "") or ""
    if business:
        lines.append(f"Business: {business}")

    for day_line in _format_course_day_lines(booking):
        lines.append(day_line)

    loc = booking.training_location
    if loc:
        loc_text = ", ".join(_location_lines(loc))
        if loc_text:
            lines.append(f"Location: {loc_text}")

    if booking.contact_name or booking.telephone:
        contact = " · ".join(b for b in (booking.contact_name, booking.telephone) if b)
        lines.append(f"Contact: {contact}")

    lines.append(f"Instructor fee: {_format_money(booking.instructor_fee)}")

    notes = (booking.booking_notes or "").strip()
    if notes:
        lines.append(f"Notes: {notes}")

    maps_url = google_maps_url_for_booking(booking)
    if maps_url:
        lines.append(f"Map: {maps_url}")

    if booking.pk:
        lines.append(f"Open in Pegasus: {absolute_url(reverse('instructor_booking_detail', args=[booking.pk]))}")

    lines.append("")
    lines.append("A PDF with the venue map, QR codes and full course details is attached.")

    body = "\n".join(line for line in lines if line is not None)
    return prepend_notification_disclaimer(body, booking, html=False)


def format_booking_email_html(
    booking,
    notification_type: str,
    *,
    intro=None,
    changed_areas=None,
    on_date=None,
    offset_days=None,
    first_date=None,
    travel_seconds=None,
    buffer_minutes=None,
    morning_today=False,
) -> str:
    pack = build_booking_pack_context(booking, on_date=on_date or first_date)
    heading = booking_email_subject(notification_type, booking).split(" — ", 1)[0]

    if notification_type == "departure_reminder" and on_date:
        if morning_today:
            telegram_body = format_morning_today_reminder_message(booking, on_date)
        else:
            from django.conf import settings

            telegram_body = format_departure_reminder_message(
                booking,
                on_date,
                travel_seconds=int(travel_seconds or 0),
                buffer_minutes=int(buffer_minutes or getattr(settings, "DEPARTURE_REMINDER_BUFFER_MINUTES", 30)),
            )
        summary_html = telegram_body.replace("\n", "<br>")
    elif notification_type.startswith("upcoming_booking_") and first_date is not None and offset_days is not None:
        summary_html = format_upcoming_booking_reminder_message(
            booking,
            offset_days=offset_days,
            first_date=first_date,
        ).replace("\n", "<br>")
    else:
        intro_lines = _email_intro_lines(
            booking,
            notification_type,
            intro=intro,
            changed_areas=changed_areas,
        )
        summary_html = "<br>".join(escape(line) for line in intro_lines if line)

    disclaimer = notification_disclaimer_lines(booking, html=True)
    disclaimer_html = "<br>".join(disclaimer) if disclaimer else ""

    return render_to_string(
        "training/emails/booking_notification.html",
        {
            "heading": heading,
            "summary_html": summary_html,
            "disclaimer_html": disclaimer_html,
            "pack": pack,
            "maps_url": pack.get("maps_url"),
            "pegasus_url": pack.get("pegasus_url"),
        },
    )

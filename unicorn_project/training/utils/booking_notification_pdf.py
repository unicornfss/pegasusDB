"""Course pack PDF for booking notification emails."""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from urllib.parse import quote

import requests
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .booking_details import (
    _format_course_day_lines,
    _format_money,
    _instructor_first_name,
    _location_lines,
    google_maps_url_for_booking,
    notification_disclaimer_lines,
)
from .register_links import qr_png_bytes
from .site_url import public_site_url
from .telegram_today import booking_feedback_form_url, booking_register_form_url

logger = logging.getLogger(__name__)

BURGUNDY = "#8b0000"
LIGHT_GREY = "#f5f5f5"
BORDER_GREY = "#cccccc"

try:
    from weasyprint import HTML  # type: ignore
except Exception:  # pragma: no cover
    HTML = None


def absolute_url(path: str) -> str:
    site = public_site_url()
    if not site:
        return path
    return f"{site}{path}"


def _png_data_uri(png_bytes: bytes | None) -> str | None:
    if not png_bytes:
        return None
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def static_map_image_bytes(booking) -> bytes | None:
    api_key = (getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "").strip()
    if not api_key:
        return None

    lat = booking.effective_precise_lat()
    lng = booking.effective_precise_lng()
    if lat is not None and lng is not None:
        center = f"{lat},{lng}"
        markers = f"color:red|{lat},{lng}"
    else:
        loc = booking.training_location
        if not loc:
            return None
        address = ", ".join(_location_lines(loc))
        if not address:
            return None
        center = quote(address)
        markers = f"color:red|{quote(address)}"

    url = (
        "https://maps.googleapis.com/maps/api/staticmap"
        f"?center={center}&zoom=16&size=700x320&scale=2&maptype=roadmap"
        f"&markers={markers}&key={api_key}"
    )
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("image/") and len(response.content) > 500:
            return response.content
        logger.warning(
            "Static map unexpected response for booking %s: %s (%s bytes)",
            booking.pk,
            content_type,
            len(response.content),
        )
    except Exception:
        logger.exception("Static map fetch failed for booking %s", booking.pk)
    return None


def _qr_entry(title: str, url: str) -> dict | None:
    url = (url or "").strip()
    if not url:
        return None
    png = qr_png_bytes(url, box_size=6, border=2)
    return {
        "title": title,
        "url": url,
        "image_bytes": png,
        "image_data_uri": _png_data_uri(png),
    }


def booking_qr_codes(booking, *, on_date=None) -> list[dict]:
    """QR codes for this booking (registration, feedback, exams)."""
    on_date = on_date or booking.course_date or timezone.localdate()
    codes: list[dict] = []
    seen_urls: set[str] = set()

    def add(title: str, url: str) -> None:
        url = (url or "").strip()
        if not url or url in seen_urls:
            return
        entry = _qr_entry(title, url)
        if entry:
            seen_urls.add(url)
            codes.append(entry)

    add("Delegate registration", booking_register_form_url(booking, on_date))
    add("Course feedback", booking_feedback_form_url(booking, on_date))

    course = getattr(booking, "course_type", None)
    course_code = (getattr(course, "code", "") or "").strip()
    if course_code:
        if not any("registration" in c["title"].lower() for c in codes):
            add(
                "Delegate registration",
                absolute_url(reverse("public_register_short", kwargs={"code": course_code})),
            )
        if not any("feedback" in c["title"].lower() for c in codes):
            add(
                "Course feedback",
                absolute_url(reverse("public_feedback_short", kwargs={"code": course_code})),
            )
        from .online_exercises import booking_accident_reports_enabled

        if booking_accident_reports_enabled(booking) and not any(
            "accident" in c["title"].lower() for c in codes
        ):
            add(
                "Accident reports",
                absolute_url(reverse("public_accident_report_short", kwargs={"code": course_code})),
            )

    if course and getattr(course, "has_exam", False):
        for exam in course.exams.order_by("sequence"):
            exam_code = (exam.exam_code or "").strip()
            if not exam_code:
                continue
            exam_url = absolute_url(reverse("public_exam_short", kwargs={"code": exam_code}))
            title = exam.title or f"Exam {exam.sequence}"
            add(f"Exam — {title}", exam_url)

    return codes


def build_booking_pack_context(booking, *, on_date=None) -> dict:
    on_date = on_date or booking.course_date or timezone.localdate()
    loc = booking.training_location
    maps_url = google_maps_url_for_booking(booking)
    map_bytes = static_map_image_bytes(booking)

    contact_bits = [b for b in (booking.contact_name, booking.telephone) if b]
    day_lines = _format_course_day_lines(booking)

    disclaimer = notification_disclaimer_lines(booking, html=False)

    pegasus_url = ""
    if booking.pk:
        pegasus_url = absolute_url(reverse("instructor_booking_detail", args=[booking.pk]))

    instructor = getattr(booking, "instructor", None)
    instructor_display = getattr(instructor, "name", "") if instructor else ""

    return {
        "booking": booking,
        "on_date": on_date,
        "instructor_name": _instructor_first_name(booking),
        "instructor_display": instructor_display,
        "course_name": getattr(booking.course_type, "name", "") or "Course",
        "business_name": getattr(booking.business, "name", "") or "",
        "location_lines": _location_lines(loc) if loc else [],
        "location_name": getattr(loc, "name", "") if loc else "",
        "day_lines": day_lines,
        "course_notes": (booking.booking_notes or "").strip(),
        "instructor_fee": _format_money(booking.instructor_fee),
        "mileage_fee": _format_money(getattr(booking, "mileage_fee", None)),
        "contact_line": " · ".join(contact_bits),
        "status_display": booking.get_status_display() if hasattr(booking, "get_status_display") else booking.status,
        "cancel_reason": (booking.cancel_reason or "").strip(),
        "maps_url": maps_url,
        "plus_code": booking.effective_plus_code() or "",
        "plus_code_url": booking.plus_code_url() if booking.effective_plus_code() else "",
        "training_address": booking.training_address_for_map() if hasattr(booking, "training_address_for_map") else "",
        "map_image_bytes": map_bytes,
        "map_image_data_uri": _png_data_uri(map_bytes),
        "qr_codes": booking_qr_codes(booking, on_date=on_date),
        "disclaimer_lines": disclaimer,
        "pegasus_url": pegasus_url,
        "office_phone": getattr(settings, "OFFICE_PHONE", ""),
        "generated_date": timezone.localdate().strftime("%d %b %Y"),
    }


def _detail_table(rows: list[tuple[str, str]]):
    """Styled two-column detail table for ReportLab."""
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Table, TableStyle

    from reportlab.lib.styles import ParagraphStyle

    label_style = ParagraphStyle(
        "PackLabel",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.HexColor("#444444"),
    )
    value_style = ParagraphStyle(
        "PackValue",
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#111111"),
        leading=12,
    )

    data = []
    for label, value in rows:
        if not value:
            continue
        data.append([
            Paragraph(label, label_style),
            Paragraph(str(value).replace("\n", "<br/>"), value_style),
        ])

    if not data:
        return None

    table = Table(data, colWidths=[38 * 2.835, 132 * 2.835])  # mm to points (~)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor(LIGHT_GREY)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(BORDER_GREY)),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(BORDER_GREY)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _render_reportlab_booking_pack(context: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    booking = context["booking"]
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Course pack {booking.course_reference or ''}",
    )

    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        "PackTitle",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=colors.white,
        spaceAfter=0,
        leading=24,
    )
    subtitle_style = ParagraphStyle(
        "PackSubtitle",
        fontSize=10,
        textColor=colors.HexColor("#ffdddd"),
        leading=13,
    )
    section_style = ParagraphStyle(
        "PackSection",
        fontSize=12,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor(BURGUNDY),
        spaceBefore=10,
        spaceAfter=6,
        borderPadding=0,
    )
    body_style = ParagraphStyle(
        "PackBody",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#333333"),
    )
    small_style = ParagraphStyle(
        "PackSmall",
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#555555"),
    )
    banner_style = ParagraphStyle(
        "PackBanner",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#664d00"),
        backColor=colors.HexColor("#fff3cd"),
        borderPadding=8,
    )

    ref = booking.course_reference or "—"
    header_table = Table(
        [[
            Paragraph("Unicorn Training", title_style),
        ], [
            Paragraph(f"Course details pack · {ref}", subtitle_style),
        ]],
        colWidths=[doc.width],
    )
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(BURGUNDY)),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (0, 0), 12),
        ("BOTTOMPADDING", (-1, -1), (-1, -1), 12),
        ("TOPPADDING", (0, 1), (0, 1), 0),
        ("BOTTOMPADDING", (0, 0), (0, 0), 4),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))

    meta_parts = [context["course_name"]]
    if context["business_name"]:
        meta_parts.append(context["business_name"])
    story.append(Paragraph(" · ".join(meta_parts), body_style))
    if context.get("instructor_display"):
        story.append(Paragraph(f"Instructor: {context['instructor_display']}", body_style))
    story.append(Spacer(1, 6))

    disclaimer_lines = [ln for ln in (context.get("disclaimer_lines") or []) if ln]
    if disclaimer_lines:
        story.append(Paragraph("<br/>".join(disclaimer_lines), banner_style))
        story.append(Spacer(1, 8))

    booking_rows = [
        ("Reference", ref),
        ("Course", context["course_name"]),
        ("Business", context["business_name"]),
        ("Status", context["status_display"]),
        ("Date(s)", "<br/>".join(context.get("day_lines") or []) or "—"),
        ("Instructor fee", context["instructor_fee"]),
    ]
    if context.get("mileage_fee") and context["mileage_fee"] != "—":
        booking_rows.append(("Mileage", context["mileage_fee"]))
    if context.get("course_notes"):
        booking_rows.append(("Course notes", context["course_notes"]))
    if context.get("cancel_reason"):
        booking_rows.append(("Cancellation reason", context["cancel_reason"]))

    story.append(Paragraph("Booking", section_style))
    booking_table = _detail_table(booking_rows)
    if booking_table:
        story.append(booking_table)

    venue_rows = []
    if context.get("location_lines"):
        venue_rows.append(("Venue", ", ".join(context["location_lines"])))
    if context.get("training_address"):
        venue_rows.append(("Address", context["training_address"]))
    if context.get("contact_line"):
        venue_rows.append(("On-site contact", context["contact_line"]))
    if context.get("plus_code"):
        venue_rows.append(("Plus code", context["plus_code"]))
    if context.get("maps_url"):
        venue_rows.append(("Directions", f'<a href="{context["maps_url"]}" color="#8b0000">{context["maps_url"]}</a>'))

    story.append(Paragraph("Venue &amp; contact", section_style))
    venue_table = _detail_table(venue_rows)
    if venue_table:
        story.append(venue_table)

    map_bytes = context.get("map_image_bytes")
    if map_bytes:
        story.append(Spacer(1, 8))
        map_img = RLImage(BytesIO(map_bytes), width=doc.width, height=doc.width * 0.42)
        map_img.hAlign = "CENTER"
        story.append(map_img)
        story.append(Paragraph("Venue map (Google Maps)", small_style))
    elif context.get("maps_url"):
        story.append(Spacer(1, 4))
        story.append(Paragraph(f'<a href="{context["maps_url"]}">Open venue in Google Maps</a>', body_style))

    qr_codes = context.get("qr_codes") or []
    if qr_codes:
        story.append(Paragraph("QR codes", section_style))
        story.append(Paragraph("Scan with a phone camera to open registration, feedback or exam forms.", body_style))
        story.append(Spacer(1, 6))

        qr_size = 32 * mm
        cells = []
        row = []
        for index, qr in enumerate(qr_codes):
            img_bytes = qr.get("image_bytes")
            parts = []
            if img_bytes:
                img = RLImage(BytesIO(img_bytes), width=qr_size, height=qr_size)
                img.hAlign = "CENTER"
                parts.append(img)
            parts.append(Paragraph(f"<b>{qr['title']}</b>", body_style))
            url_short = qr["url"]
            if len(url_short) > 55:
                url_short = url_short[:52] + "…"
            parts.append(Paragraph(url_short, small_style))

            cell_table = Table([[p] for p in parts], colWidths=[qr_size + 8 * mm])
            cell_table.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(BORDER_GREY)),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            row.append(cell_table)
            if len(row) == 2:
                cells.append(row)
                row = []
        if row:
            if len(row) == 1:
                row.append("")
            cells.append(row)

        qr_grid = Table(cells, colWidths=[doc.width / 2.0 - 4, doc.width / 2.0 - 4])
        qr_grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(qr_grid)

    footer_bits = ["Unicorn Fire &amp; Safety Training"]
    if context.get("office_phone"):
        footer_bits.append(context["office_phone"])
    if context.get("pegasus_url"):
        footer_bits.append(f'Pegasus: <a href="{context["pegasus_url"]}">{context["pegasus_url"]}</a>')
    footer_bits.append(f"Generated {context.get('generated_date', '')}")

    story.append(Spacer(1, 12))
    story.append(Paragraph(" · ".join(footer_bits), small_style))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def render_booking_notification_pdf(booking, *, on_date=None) -> tuple[bytes, str, str]:
    """
    Render the course details PDF attached to booking notification emails.
    Returns (bytes, filename, content_type).
    """
    context = build_booking_pack_context(booking, on_date=on_date)
    ref = booking.course_reference or str(booking.pk)
    filename = f"course-pack-{ref}.pdf"
    context["filename"] = filename

    if HTML is not None:
        try:
            html_str = render_to_string("training/booking_notification_pack.html", context)
            pdf_bytes = HTML(
                string=html_str,
                base_url=str(getattr(settings, "BASE_DIR", "")),
            ).write_pdf()
            if pdf_bytes and len(pdf_bytes) > 5000:
                return pdf_bytes, filename, "application/pdf"
        except Exception:
            logger.exception("WeasyPrint failed for booking pack %s", booking.pk)

    return _render_reportlab_booking_pack(context), filename, "application/pdf"


def booking_course_pack_pdf_response(booking, *, on_date=None):
    """HTTP response that opens the course pack PDF in the browser."""
    from django.http import HttpResponse

    pdf_bytes, filename, mimetype = render_booking_notification_pdf(booking, on_date=on_date)
    response = HttpResponse(pdf_bytes, content_type=mimetype)
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response

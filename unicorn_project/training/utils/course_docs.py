"""
Utilities to build & email course PDFs to admin.

Place this file at:
unicorn_project/training/utils/course_docs.py
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from django.conf import settings
from django.core.mail import EmailMessage
from django.http import HttpResponse

from ..models import Booking, BookingDay
from .certificates import build_certificates_pdf_for_booking

def _safe_attach_pdf(msg: EmailMessage, fname: str, data: bytes, ctype: str = "application/pdf") -> bool:
    """
    Attach only non-empty PDF bytes. Return True if attached, False otherwise.
    """
    if not data:
        return False
    # accept when explicit PDF mimetype, or filename ends with .pdf
    if (ctype or "").lower() != "application/pdf" and not fname.lower().endswith(".pdf"):
        return False
    msg.attach(fname, data, "application/pdf")
    return True

def _response_bytes(resp: HttpResponse) -> Tuple[bytes, str, str]:
    """
    Normalise a view response (HttpResponse or FileResponse) to (bytes, filename, content_type).
    """
    ctype = resp.get("Content-Type", "application/pdf")

    # body
    try:
        body = resp.content  # HttpResponse
    except Exception:
        body = b"".join(resp.streaming_content)  # FileResponse (streaming)

    # filename from Content-Disposition if available
    cd = resp.get("Content-Disposition", "")
    fname = "document.pdf"
    if "filename=" in cd:
        part = cd.split("filename=", 1)[1].strip().strip('"').strip("'")
        if part:
            fname = part

    return body, fname, ctype


def _admin_recipient() -> str:
    """
    In DEV: use DEV_CATCH_ALL_EMAIL (e.g. Hotmail).
    In PROD: ADMIN_EMAIL or ADMIN_INBOX_EMAIL; fallback to info@unicornsafety.co.uk.
    """
    if getattr(settings, "DEBUG", False):
        return getattr(settings, "DEV_CATCH_ALL_EMAIL", "jon.ostrowski@hotmail.com")
    return (
        getattr(settings, "ADMIN_EMAIL", None)
        or getattr(settings, "ADMIN_INBOX_EMAIL", None)
        or "info@unicornsafety.co.uk"
    )


def _subject_for(booking: Booking) -> str:
    ref = booking.course_reference or ""
    return f"[Unicorn] Course documents for {booking.course_type.name} {f'({ref})' if ref else ''}"


def _collect_register_pdfs(request, booking: Booking) -> List[Tuple[str, bytes]]:
    """
    Call existing per-day PDF view for each BookingDay and return list of (filename, bytes).
    """
    from ..views_instructor import instructor_day_registers_pdf  # local import to avoid cycles

    out: List[Tuple[str, bytes]] = []
    for day in BookingDay.objects.filter(booking=booking).order_by("date"):
        resp = instructor_day_registers_pdf(request, pk=day.id)
        data, fname, _ctype = _response_bytes(resp)
        if not fname.lower().endswith(".pdf"):
            fname = f"register_{day.date.isoformat()}.pdf"
        out.append((fname, data))
    return out


def _collect_feedback_pdf(request, booking: Booking) -> Optional[Tuple[str, bytes]]:
    """
    Call existing 'all feedback' PDF view, return (filename, bytes) or None if it fails.
    """
    try:
        from ..views_instructor import instructor_feedback_pdf_all  # local import to avoid cycles

        resp = instructor_feedback_pdf_all(request, booking.id)
        data, fname, _ctype = _response_bytes(resp)
        if not fname.lower().endswith(".pdf"):
            fname = "feedback_all.pdf"
        return (fname, data)
    except Exception:
        return None


def _collect_assessment_pdf(request, booking: Booking) -> Optional[Tuple[str, bytes]]:
    """
    Optional: Assessment matrix PDF if your project provides a view named
    `instructor_assessment_pdf`. If not available or it raises, skip silently.
    """
    try:
        from ..views_instructor import instructor_assessment_pdf  # type: ignore

        resp = instructor_assessment_pdf(request, booking.id)  # type: ignore
        data, fname, _ctype = _response_bytes(resp)
        if not fname.lower().endswith(".pdf"):
            fname = "assessment_matrix.pdf"
        return (fname, data)
    except Exception:
        return None

def _collect_course_summary_pdf(request, booking: Booking) -> Optional[Tuple[str, bytes]]:
    """
    Build the Course Summary PDF directly (no HTTP view call) and return
    (filename, bytes) or None if something fails.
    """
    try:
        from django.template.loader import render_to_string
        from weasyprint import HTML

        # --- Build pass/fail/dnf (dedupe across days) ---
        from ..models import DelegateRegister  # local import avoids cycles

        regs_qs = (
            DelegateRegister.objects
            .filter(booking_day__booking=booking)
            .only("name", "outcome")
        )

        priority = {"pass": 3, "fail": 2, "dnf": 1, "did not finish": 1, "did_not_finish": 1}
        best: dict[str, str] = {}
        for r in regs_qs:
            name = (r.name or "").strip()
            outcome = str(r.outcome or "").strip().lower()
            if not name:
                continue
            if best.get(name) is None or priority.get(outcome, 0) > priority.get(best[name], 0):
                best[name] = outcome

        passed = sorted([n for n, o in best.items() if o == "pass"])
        failed = sorted([n for n, o in best.items() if o == "fail"])
        dnf    = sorted([n for n, o in best.items() if priority.get(o, 0) == 1])

        # End date for header
        end_date = (
            booking.days.order_by("date").values_list("date", flat=True).last()
            or booking.course_date
        )

        ctx = {
            "booking": booking,
            "end_date": end_date,
            "passed": passed,
            "failed": failed,
            "dnf": dnf,
        }

        # Render HTML
        html = render_to_string("training/course_summary.html", ctx)

        # Base URL for assets (images/css) if needed
        if request is not None:
            base_url = request.build_absolute_uri("/")
        else:
            base_url = getattr(settings, "SITE_URL", None) or "https://{}".format(
                (settings.ALLOWED_HOSTS or ["localhost"])[0]
            ).rstrip("/") + "/"

        # Generate PDF bytes
        pdf_bytes = HTML(string=html, base_url=base_url).write_pdf()
        if not pdf_bytes:
            return None

        ref = booking.course_reference or str(booking.pk)
        fname = f"course-summary-{ref}.pdf"
        return (fname, pdf_bytes)

    except Exception:
        # Be silent here; caller will just skip attaching
        return None



def email_all_course_docs_to_admin(request, booking: Booking) -> int:
    """
    Build all course PDFs and send one email to admin.
    Returns number of attachments actually sent.
    """
    to_addr = _admin_recipient()
    subject = _subject_for(booking)
    body = (
        "Please find attached the course documents.\n\n"
        f"Course: {booking.course_type.name}\n"
        f"Reference: {booking.course_reference or '-'}\n"
        f"Location: {getattr(booking.training_location, 'name', '-')}\n"
        f"Instructor: {getattr(booking.instructor, 'name', '-')}\n"
    )

    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None) or to_addr,
        to=[to_addr],
    )

    count = 0

    # Registers (per day)
    for fname, data in _collect_register_pdfs(request, booking):
        # Treat registers as PDFs by definition
        if _safe_attach_pdf(msg, fname, data, "application/pdf"):
            count += 1

    # Feedback (all)
    fb = _collect_feedback_pdf(request, booking)
    if fb:
        fname, data = fb
        if _safe_attach_pdf(msg, fname, data, "application/pdf"):
            count += 1

    # Assessment matrix (optional)
    assess = _collect_assessment_pdf(request, booking)
    if assess:
        fname, data = assess
        if _safe_attach_pdf(msg, fname, data, "application/pdf"):
            count += 1

     # Course summary (optional)
    summary = _collect_course_summary_pdf(request, booking)
    if summary:
        fname, data = summary
        if _safe_attach_pdf(msg, fname, data, "application/pdf"):
            count += 1

    # Certificates (all delegates, one combined PDF)
    cert = build_certificates_pdf_for_booking(booking)
    if cert:
        fname, data = cert
        if _safe_attach_pdf(msg, fname, data, "application/pdf"):
            count += 1

    # Always send — even if count==0, you still want the body to arrive
    msg.send(fail_silently=False)
    return count

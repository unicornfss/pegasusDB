import os
from datetime import date
from io import BytesIO
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.template.loader import render_to_string
from django.contrib.staticfiles import finders

from xhtml2pdf import pisa

from ..models import Booking, DelegateRegister



# Static business info (from your message)
BUSINESS_NAME = "Unicorn Fire & Safety Solutions Ltd"
BUSINESS_CONTACT_NUMBER = "01743 360211"
BUSINESS_EMAIL = "info@unicornsafety.co.uk"


def _unique_delegates_for_booking(booking: Booking) -> List[DelegateRegister]:
    """
    Return one DelegateRegister per unique delegate (name + date_of_birth) for this booking,
    but ONLY for delegates who achieved a 'Pass'.

    This prevents certificates being generated for fails / DNFs.
    """
    qs = (
        DelegateRegister.objects
        .filter(
            booking_day__booking=booking,
            outcome__iexact="pass",   # <- only passes
        )
        .order_by("name", "date_of_birth")
    )

    seen: Dict[tuple, DelegateRegister] = {}
    for reg in qs:
        key = (
            (reg.name or "").strip(),
            reg.date_of_birth,  # can be None
        )
        if key not in seen:
            seen[key] = reg

    return list(seen.values())




def _certificate_expiry_date_for_booking(booking: Booking) -> Optional[date]:
    """
    Simple rule: certificate valid for 3 years from course_date.
    Adjust later if you have per-course duration logic.
    """
    base = getattr(booking, "course_date", None)
    if not base:
        return None

    try:
        return base.replace(year=base.year + 3)
    except Exception:
        # Fallback if 29 Feb etc. causes an issue
        return base


def _format_date(d: Optional[date]) -> str:
    if not d:
        return "-"
    return d.strftime("%d %B %Y")


def _html_to_pdf_bytes(html: str) -> bytes:
    """
    Convert HTML string to PDF bytes using xhtml2pdf (pisa).
    Logs errors to the console for debugging.
    """
    pdf_io = BytesIO()
    result = pisa.CreatePDF(html, dest=pdf_io)
    if result.err:
        print(f"[certificates] xhtml2pdf reported {result.err} error(s) when creating PDF")
    pdf_io.seek(0)
    return pdf_io.getvalue()


def build_certificates_pdf_for_booking(booking: Booking) -> Optional[Tuple[str, bytes]]:
    """
    Build a single PDF containing one certificate page per delegate on this booking.

    Uses:
      - Django HTML template: training/certificates.html
      - xhtml2pdf for HTML -> PDF

    Returns (filename, pdf_bytes) or None if there are no delegates.
    """
    delegates = _unique_delegates_for_booking(booking)
    print(f"[certificates] Found {len(delegates)} unique delegates for booking {booking.pk}")

    if not delegates:
        return None

    course_date_str = _format_date(getattr(booking, "course_date", None))
    expiry_date = _certificate_expiry_date_for_booking(booking)
    expiry_str = _format_date(expiry_date)

    certificates = []
    for reg in delegates:
        certificates.append({
            "delegate_name": reg.name,
            "course_title": booking.course_type.name,
            "course_date": course_date_str,
            "certificate_expiry_date": expiry_str,
            "business_name": BUSINESS_NAME,
            "business_contact_number": BUSINESS_CONTACT_NUMBER,
            "business_email": BUSINESS_EMAIL,
        })

    # Look up logo via Django staticfiles so the path is always correct
    logo_path = (
        finders.find("training/img/logo.png")
        or finders.find("training/img/logo_poppy.png")
    )
    if logo_path and os.path.exists(logo_path):
        logo_src = logo_path  # plain filesystem path for xhtml2pdf
        print(f"[certificates] Using logo at {logo_src}")
    else:
        logo_src = None
        print("[certificates] Logo file not found via staticfiles; skipping logo.")

    # Watermark (optional, pale logo)
    wm_path = finders.find("training/img/logo_watermark.png")
    if wm_path and os.path.exists(wm_path):
        watermark_src = wm_path
        print(f"[certificates] Using watermark at {watermark_src}")
    else:
        watermark_src = None
        print("[certificates] Watermark image not found; skipping watermark.")

    ctx = {
        "booking": booking,
        "certificates": certificates,
        "logo_src": logo_src,
        "watermark_src": watermark_src,
    }

    html = render_to_string("training/certificates.html", ctx)
    pdf_bytes = _html_to_pdf_bytes(html)

    if not pdf_bytes:
        print("[certificates] Generated PDF bytes are empty; not attaching certificates.")
        return None

    ref = booking.course_reference or str(booking.pk)
    filename = f"certificates-{ref}.pdf"
    print(f"[certificates] Built certificates PDF for booking {booking.pk}: {filename}")
    return filename, pdf_bytes

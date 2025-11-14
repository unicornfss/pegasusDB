from __future__ import annotations

import os
from datetime import date
from io import BytesIO
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.contrib.staticfiles import finders

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from ..models import Booking, DelegateRegister


# -------------------------------------------------------------------
# Font registration helpers
# -------------------------------------------------------------------

FONTS_REGISTERED = False


def _register_certificate_fonts() -> None:
    """
    Register Georgia (regular + bold) and Calibri with ReportLab.
    Looks for TTFs under static/training/fonts.
    """
    global FONTS_REGISTERED
    if FONTS_REGISTERED:
        return

    fonts_dir = os.path.join(
        settings.BASE_DIR,
        "unicorn_project",
        "training",
        "static",
        "training",
        "fonts",
    )

    def _font_path(*names: str) -> Optional[str]:
        """
        Try each name in order under fonts_dir, return the first that exists.
        """
        for name in names:
            p = os.path.join(fonts_dir, name)
            if os.path.exists(p):
                return p
        return None

    georgia_regular = _font_path("Georgia.ttf", "georgia.ttf")
    georgia_bold = _font_path("Georgia-Bold.ttf", "georgiab.ttf")
    calibri_regular = _font_path("Calibri.ttf", "calibri.ttf")

    if georgia_regular:
        pdfmetrics.registerFont(TTFont("Georgia", georgia_regular))
    else:
        print("[certificates] Georgia regular font not found; falling back to built-in fonts.")

    if georgia_bold:
        pdfmetrics.registerFont(TTFont("Georgia-Bold", georgia_bold))
    else:
        print("[certificates] Georgia bold font not found; falling back to Georgia/Helvetica.")

    if calibri_regular:
        pdfmetrics.registerFont(TTFont("Calibri", calibri_regular))
    else:
        print("[certificates] Calibri font not found; falling back to Helvetica.")

    FONTS_REGISTERED = True


# -------------------------------------------------------------------
# Delegate selection / date helpers
# -------------------------------------------------------------------

def _unique_delegates_for_booking(booking: Booking) -> List[DelegateRegister]:
    """
    Return one DelegateRegister per unique delegate (name + date_of_birth)
    for this booking, but ONLY for delegates who achieved a 'Pass'.

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


# -------------------------------------------------------------------
# PDF builder (ReportLab + PNG background)
# -------------------------------------------------------------------

def build_certificates_pdf_for_booking(booking: Booking) -> Optional[Tuple[str, bytes]]:
    """
    Build a single PDF containing one certificate page per delegate on this booking,
    using the designed PNG background and ReportLab for text overlay.

    Dynamic fields:
      - Delegate name
      - Course title
      - Course end date
      - Certificate expiry date
      - Instructor name + signature

    Returns (filename, pdf_bytes) or None if there are no delegates or background missing.
    """
    _register_certificate_fonts()

    delegates = _unique_delegates_for_booking(booking)
    print(f"[certificates] Found {len(delegates)} unique delegates for booking {booking.pk}")
    if not delegates:
        return None

    # Course end date (you can change this if you want last BookingDay instead)
    course_date_str = _format_date(getattr(booking, "course_date", None))
    expiry_date = _certificate_expiry_date_for_booking(booking)
    expiry_str = _format_date(expiry_date)

    course_title = booking.course_type.name

    # Instructor name (used for text + signature initials)
    instructor_name = ""
    if getattr(booking, "instructor", None):
        instructor_name = getattr(booking.instructor, "name", "") or ""

    # Background PNG via staticfiles
    bg_path = (
        finders.find("training/img/certificate.png")
        or os.path.join(
            settings.BASE_DIR,
            "unicorn_project",
            "training",
            "static",
            "training",
            "img",
            "certificate.png",
        )
    )
    if not bg_path or not os.path.exists(bg_path):
        print("[certificates] certificate.png not found; cannot build certificates PDF.")
        return None

    bg_image = ImageReader(bg_path)

    # Page size: A4 landscape
    page_width, page_height = landscape(A4)

    # Prepare PDF in memory
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_width, page_height))

    # Colours
    PURPLE = (0x83 / 255.0, 0x39 / 255.0, 0x78 / 255.0)  # #833978
    GREY = (0x7F / 255.0, 0x7F / 255.0, 0x7F / 255.0)    # #7F7F7F

    # Helper fonts (fall back if registration failed)
    name_font = "Georgia-Bold" if "Georgia-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    georgia_font = "Georgia-Bold" if "Georgia-Bold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    calibri_font = "Calibri" if "Calibri" in pdfmetrics.getRegisteredFontNames() else "Helvetica"

    # Coordinates are fractions of page width/height so they scale with A4.
    # You can tweak these if the positioning needs nudging for your updated PNG.
    for reg in delegates:
        delegate_name = reg.name or ""

        # Full-page background
        c.drawImage(
            bg_image,
            0,
            0,
            width=page_width,
            height=page_height,
            preserveAspectRatio=True,
            mask="auto",
        )

        # Delegate name – directly under "This is to certify that"
        c.setFillColorRGB(*PURPLE)
        c.setFont(name_font, 47)
        c.drawCentredString(page_width * 0.66, page_height * 0.62, delegate_name)

        # Course name – under "Has attended and passed a" (slightly lower)
        c.setFont(georgia_font, 21)
        c.drawCentredString(page_width * 0.66, page_height * 0.49, course_title)

        # Course end date – centred under "Certificate date" (drop under label)
        c.setFont(georgia_font, 18)
        c.drawCentredString(page_width * 0.58, page_height * 0.365, course_date_str)

        # Expiry date – centred under "Expiry date" (drop under label)
        c.drawCentredString(page_width * 0.80, page_height * 0.365, expiry_str)

        # Instructor name – directly above the word "Instructor"
        if instructor_name:
            c.setFillColorRGB(*GREY)
            c.setFont(calibri_font, 14)
            inst_name_x = page_width * 0.76
            inst_name_y = page_height * 0.175

            c.drawCentredString(inst_name_x, inst_name_y, instructor_name)

            # Instructor signature image based on initials
            initials = "".join([p[0].upper() for p in instructor_name.split() if p])
            sig_rel = f"training/img/instructor_signatures/{initials}.png"
            sig_path = finders.find(sig_rel) or os.path.join(
                settings.BASE_DIR,
                "unicorn_project",
                "training",
                "static",
                "training",
                "img",
                "instructor_signatures",
                f"{initials}.png",
            )
            
            if sig_path and os.path.exists(sig_path):
                try:
                    # Optional: log size so you can confirm it's the new file
                    try:
                        size = os.path.getsize(sig_path)
                        print(f"[certificates] Using signature {sig_path} ({size} bytes) for {initials}")
                    except OSError:
                        pass

                    # Load a fresh ImageReader from the file object to avoid path-based caching
                    with open(sig_path, "rb") as f:
                        sig_img = ImageReader(f)

                    sig_width = page_width * 0.2  # adjust to taste
                    sig_height = sig_width * 0.4  # keep roughly signature proportions
                    x = page_width * 0.71
                    y = page_height * 0.175  # signature on the line

                    c.drawImage(
                        sig_img,
                        x,
                        y,
                        width=sig_width,
                        height=sig_height,
                        preserveAspectRatio=True,
                        mask="auto",
                    )

                except Exception as e:
                    print(f"[certificates] Failed to draw signature for {initials}: {e}")


        c.showPage()

    c.save()
    buf.seek(0)
    pdf_bytes = buf.getvalue()

    ref = booking.course_reference or str(booking.pk)
    filename = f"certificates-{ref}.pdf"
    print(f"[certificates] Built certificates PDF for booking {booking.pk}: {filename}")
    return filename, pdf_bytes

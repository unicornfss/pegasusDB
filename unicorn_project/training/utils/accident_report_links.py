"""Public accident report form URLs (booking ref or course-type QR)."""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse

from .register_links import qr_png_bytes
from .site_url import public_site_url

__all__ = [
    "booking_accident_report_form_url",
    "course_accident_report_short_path",
    "course_accident_report_short_url",
    "course_accident_report_full_url",
    "qr_png_bytes",
]


def booking_accident_report_form_url(booking) -> str:
    site = public_site_url()
    ref = (getattr(booking, "course_reference", "") or "").strip()
    if not site or not ref:
        return ""
    params = {"ref": ref}
    return f"{site}{reverse('accident_report_public')}?{urlencode(params)}"


def course_accident_report_short_path(course_code: str) -> str:
    return reverse("public_accident_report_short", kwargs={"code": course_code})


def course_accident_report_short_url(request, course_code: str) -> str:
    return request.build_absolute_uri(course_accident_report_short_path(course_code))


def course_accident_report_full_url(request, course_code: str) -> str:
    query = urlencode({"course": course_code})
    return request.build_absolute_uri(f"{reverse('accident_report_public')}?{query}")

"""Short URLs and QR codes for delegate exam entry."""
from urllib.parse import urlencode

from django.urls import reverse

from .register_links import qr_png_bytes


def exam_short_path(exam_code: str) -> str:
    return reverse("public_exam_short", kwargs={"code": exam_code})


def exam_short_url(request, exam_code: str) -> str:
    return request.build_absolute_uri(exam_short_path(exam_code))


def exam_full_url(request, exam_code: str) -> str:
    query = urlencode({"examcode": exam_code})
    return request.build_absolute_uri(f"{reverse('delegate_exam_start')}?{query}")

from urllib.parse import urlencode

from django.urls import reverse

from .register_links import qr_png_bytes

__all__ = [
    "course_feedback_short_path",
    "course_feedback_short_url",
    "course_feedback_full_url",
    "qr_png_bytes",
]


def course_feedback_short_path(course_code: str) -> str:
    return reverse("public_feedback_short", kwargs={"code": course_code})


def course_feedback_short_url(request, course_code: str) -> str:
    return request.build_absolute_uri(course_feedback_short_path(course_code))


def course_feedback_full_url(request, course_code: str) -> str:
    query = urlencode({"course": course_code})
    return request.build_absolute_uri(f"{reverse('public_feedback_form')}?{query}")

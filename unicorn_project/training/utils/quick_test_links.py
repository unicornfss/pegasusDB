"""Shared Quick test public-form links for dummy bookings and DEBUG."""

from __future__ import annotations

from django.conf import settings

from ..models import Exam


def attach_quick_test_links_context(ctx, booking, *, days=None) -> None:
    """
    Add:
      show_quick_test_links
      show_dev_quick_test  (DEBUG and not dummy — for the yellow banner)
      quick_test_days
      quick_test_last_day
      quick_test_exam_day_pairs
    """
    if not booking or not getattr(booking, "pk", None):
        ctx["show_quick_test_links"] = False
        ctx["show_dev_quick_test"] = False
        ctx["quick_test_days"] = []
        ctx["quick_test_last_day"] = None
        ctx["quick_test_exam_day_pairs"] = []
        return

    is_dummy = bool(getattr(booking, "is_dummy_business", False))
    show = is_dummy or bool(settings.DEBUG)
    ctx["show_quick_test_links"] = show
    ctx["show_dev_quick_test"] = bool(settings.DEBUG and not is_dummy)

    if not show:
        ctx["quick_test_days"] = []
        ctx["quick_test_last_day"] = None
        ctx["quick_test_exam_day_pairs"] = []
        return

    if days is None:
        day_list = list(booking.days.order_by("date", "id"))
    else:
        day_list = list(days)

    ctx["quick_test_days"] = day_list
    ctx["quick_test_last_day"] = day_list[-1] if day_list else None

    course_type = getattr(booking, "course_type", None)
    if course_type and getattr(course_type, "has_exam", False):
        exams_list = list(
            Exam.objects.filter(course_type=course_type).order_by("sequence", "id")
        )
        ctx["quick_test_exam_day_pairs"] = [
            (exams_list[i], day_list[i] if i < len(day_list) else None)
            for i in range(len(exams_list))
        ]
    else:
        ctx["quick_test_exam_day_pairs"] = []

    # Back-compat alias used by older templates
    ctx["dummy_exam_day_pairs"] = ctx["quick_test_exam_day_pairs"]

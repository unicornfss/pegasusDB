"""Bookable course type queryset helpers."""

from django.db.models import Q

from ..models import CourseType


def bookable_course_types(*, include_pk=None):
    """
    Course types available for new bookings / public registration.
    Optionally include a specific pk (e.g. the type on an existing booking being edited).
    """
    qs = CourseType.objects.filter(is_suspended=False)
    if include_pk:
        qs = CourseType.objects.filter(Q(is_suspended=False) | Q(pk=include_pk))
    return qs.order_by("name")

"""Accident report access and booking-scoped queries."""

from __future__ import annotations

from ..models import AccidentReport
from ..services.dummy_bookings import admin_may_view_booking
from .instructor_access import instructor_can_access_booking
from .online_exercises import booking_accident_reports_enabled


def accident_reports_for_booking(booking):
    return (
        AccidentReport.objects.filter(booking=booking)
        .select_related("reported_to")
        .order_by("-date", "-time", "-id")
    )


def booking_accident_reports_enabled_for_course_type(course_type) -> bool:
    from ..models import CourseTypeOnlineExercise

    if not course_type or not getattr(course_type, "has_online_exercises", False):
        return False
    return course_type.online_exercises.filter(
        exercise_key=CourseTypeOnlineExercise.EXERCISE_ACCIDENT_REPORTS
    ).exists()


def booking_incident_dates(booking) -> set:
    """Dates when this booking has course days."""
    dates = set(booking.days.values_list("date", flat=True))
    if booking.course_date:
        dates.add(booking.course_date)
    return {d for d in dates if d}


def incident_date_on_booking(booking, incident_date) -> bool:
    if not booking or not incident_date:
        return False
    return incident_date in booking_incident_dates(booking)


def default_incident_date_for_booking(booking):
    from django.utils import timezone as tz

    dates = sorted(booking_incident_dates(booking))
    if not dates:
        return booking.course_date or tz.localdate()
    today = tz.localdate()
    if today in dates:
        return today
    for d in dates:
        if d >= today:
            return d
    return dates[-1]


def default_incident_date_for_course(course):
    """Nearest relevant course day for this course type (today if on course, else next/future day)."""
    from django.utils import timezone as tz

    from ..models import BookingDay

    if not course:
        return tz.localdate()

    active_statuses = ("scheduled", "in_progress", "awaiting_closure", "completed")
    dates = list(
        BookingDay.objects.filter(
            booking__course_type=course,
            booking__status__in=active_statuses,
        )
        .values_list("date", flat=True)
        .distinct()
        .order_by("date")
    )
    if not dates:
        return tz.localdate()

    today = tz.localdate()
    if today in dates:
        return today
    for d in dates:
        if d >= today:
            return d
    return dates[-1]


def instructors_for_accident_report_course_date(course, day_date):
    """
    Instructors delivering this course type on a given date.
    Uses the day-level instructor when set, otherwise the booking instructor.
    One entry per person (same rules as the public register form).
    """
    from ..models import Personnel
    from .public_sessions import matching_booking_days

    if not course or not day_date:
        return []
    if not booking_accident_reports_enabled_for_course_type(course):
        return []

    seen: set = set()
    ordered_ids: list = []
    for day in matching_booking_days(course, day_date, instructor=None):
        inst = day.instructor or day.booking.instructor
        if inst and inst.pk not in seen:
            seen.add(inst.pk)
            ordered_ids.append(inst.pk)

    return list(Personnel.objects.filter(pk__in=ordered_ids).order_by("name"))


def instructors_for_booking_report(booking, incident_date=None):
    """Instructors tied to this booking (optionally for one course day)."""
    from ..models import Personnel

    ids: set = set()
    days = booking.days.select_related("instructor", "booking__instructor")
    if incident_date:
        days = days.filter(date=incident_date)
    for day in days:
        inst = day.instructor or booking.instructor
        if inst:
            ids.add(inst.pk)
    if not ids and booking.instructor_id:
        ids.add(booking.instructor_id)

    return list(Personnel.objects.filter(pk__in=ids).order_by("name"))


def resolve_accident_report_booking(*, booking_ref="", course=None, incident_date=None, reported_to=None, day_code=""):
    """Match a submitted report to a booking when possible."""
    from ..models import Booking
    from .public_sessions import resolve_booking_day

    ref = (booking_ref or "").strip()
    if ref:
        booking = (
            Booking.objects.filter(course_reference__iexact=ref)
            .select_related("course_type", "instructor")
            .prefetch_related("days")
            .first()
        )
        if booking and booking_accident_reports_enabled(booking):
            if incident_date is None or incident_date_on_booking(booking, incident_date):
                return booking

    if not course or not incident_date or not reported_to:
        return None

    if not booking_accident_reports_enabled_for_course_type(course):
        return None

    booking_day = resolve_booking_day(
        course,
        incident_date,
        reported_to,
        day_code=day_code,
    )
    return booking_day.booking if booking_day else None


def user_may_view_booking_accident_reports(user, booking) -> bool:
    if not user or not user.is_authenticated:
        return False
    personnel = getattr(user, "personnel", None)
    if personnel and instructor_can_access_booking(personnel, booking):
        return True
    return admin_may_view_booking(user, booking)


def user_may_view_accident_report(user, report) -> bool:
    if not user or not user.is_authenticated:
        return False
    if report.booking_id:
        return user_may_view_booking_accident_reports(user, report.booking)
    personnel = getattr(user, "personnel", None)
    return bool(personnel or getattr(user, "is_staff", False))


def booking_accident_reports_context(request, booking, *, portal: str) -> dict:
    from django.urls import reverse

    if portal == "admin":
        poll_url = reverse("admin_booking_accident_reports_poll", args=[booking.pk])
        export_url = reverse("admin_booking_accident_reports_export", args=[booking.pk])
        delete_url = reverse("admin_booking_accident_reports_delete", args=[booking.pk])
        anonymise_url = reverse("admin_booking_accident_reports_anonymise", args=[booking.pk])
    else:
        poll_url = reverse("instructor_booking_accident_reports_poll", args=[booking.pk])
        export_url = reverse("instructor_booking_accident_reports_export", args=[booking.pk])
        delete_url = reverse("instructor_booking_accident_reports_delete", args=[booking.pk])
        anonymise_url = reverse("instructor_booking_accident_reports_anonymise", args=[booking.pk])

    return {
        "booking": booking,
        "accident_reports": accident_reports_for_booking(booking),
        "accident_report_poll_url": poll_url,
        "accident_report_export_url": export_url,
        "accident_report_delete_url": delete_url,
        "accident_report_anonymise_url": anonymise_url,
        "has_accident_reports": booking_accident_reports_enabled(booking),
    }

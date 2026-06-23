"""Course-type online delegate exercises (accident reports, etc.)."""

from __future__ import annotations

from ..models import CourseTypeOnlineExercise

ONLINE_EXERCISE_CHOICES = CourseTypeOnlineExercise.EXERCISE_CHOICES

EXERCISE_TAB_LABELS = {
    CourseTypeOnlineExercise.EXERCISE_ACCIDENT_REPORTS: "Accident reports",
}


def course_type_exercise_keys(course_type) -> set[str]:
    if not course_type or not getattr(course_type, "has_online_exercises", False):
        return set()
    return set(course_type.online_exercises.values_list("exercise_key", flat=True))


def course_type_has_exercise(course_type, exercise_key: str) -> bool:
    return exercise_key in course_type_exercise_keys(course_type)


def booking_has_exercise(booking, exercise_key: str) -> bool:
    if not booking or not booking.course_type_id:
        return False
    return course_type_has_exercise(booking.course_type, exercise_key)


def course_types_with_accident_reports():
    from ..models import CourseType, CourseTypeOnlineExercise

    return CourseType.objects.filter(
        has_online_exercises=True,
        online_exercises__exercise_key=CourseTypeOnlineExercise.EXERCISE_ACCIDENT_REPORTS,
        is_suspended=False,
    ).distinct().order_by("name")


def booking_accident_reports_enabled(booking) -> bool:
    return booking_has_exercise(booking, CourseTypeOnlineExercise.EXERCISE_ACCIDENT_REPORTS)


def exercise_tab_id(exercise_key: str) -> str:
    return exercise_key.replace("_", "-")


def exercise_tab_label(exercise_key: str) -> str:
    return EXERCISE_TAB_LABELS.get(exercise_key, exercise_key.replace("_", " ").title())

"""Detect booking edits that should trigger a Telegram update notification."""

from __future__ import annotations

from typing import Any

CHANGE_COURSE_NOTES = "course_notes"
CHANGE_DATES_TIMES = "dates_times"
CHANGE_INSTRUCTOR_FEE = "instructor_fee"
CHANGE_CANCELLATION = "cancellation"
CHANGE_REINSTATEMENT = "reinstatement"

CHANGE_LABELS = {
    CHANGE_COURSE_NOTES: "Course notes",
    CHANGE_DATES_TIMES: "Dates / times",
    CHANGE_INSTRUCTOR_FEE: "Instructor fee",
    CHANGE_CANCELLATION: "Cancellation",
    CHANGE_REINSTATEMENT: "Reinstatement",
}


def _time_key(value) -> str:
    if not value:
        return ""
    return value.strftime("%H:%M")


def _date_key(value) -> str:
    if not value:
        return ""
    return value.isoformat()


def _money_key(value) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


def booking_notification_snapshot(booking) -> dict[str, Any] | None:
    """Capture fields watched for update notifications."""
    if not booking or not booking.pk:
        return None

    days = list(booking.days.order_by("date", "start_time", "end_time"))
    return {
        "booking_notes": (booking.booking_notes or "").strip(),
        "instructor_fee": _money_key(booking.instructor_fee),
        "course_date": _date_key(booking.course_date),
        "start_time": _time_key(booking.start_time),
        "days": [
            (_date_key(day.date), _time_key(day.start_time), _time_key(day.end_time))
            for day in days
        ],
    }


def detect_notifiable_booking_changes(
    before: dict[str, Any] | None,
    booking,
) -> list[str]:
    """
    Return change area keys that warrant an update notification.
    Empty list means no notification should be sent.
    """
    if not before:
        return []

    after = booking_notification_snapshot(booking)
    if not after:
        return []

    changes: list[str] = []

    if before["booking_notes"] != after["booking_notes"]:
        changes.append(CHANGE_COURSE_NOTES)

    if before["instructor_fee"] != after["instructor_fee"]:
        changes.append(CHANGE_INSTRUCTOR_FEE)

    schedule_before = (
        before["course_date"],
        before["start_time"],
        before["days"],
    )
    schedule_after = (
        after["course_date"],
        after["start_time"],
        after["days"],
    )
    if schedule_before != schedule_after:
        changes.append(CHANGE_DATES_TIMES)

    return changes


def format_changed_areas_label(changed_areas: list[str]) -> str:
    labels = [CHANGE_LABELS[key] for key in changed_areas if key in CHANGE_LABELS]
    return " · ".join(labels)

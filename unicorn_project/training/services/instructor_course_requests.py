"""Instructor requests to deliver additional course types."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import (
    CourseType,
    InstructorCourseRequest,
    InstructorCourseRequestStatus,
    Personnel,
    StaffInboxItemStatus,
)
from .staff_inbox import (
    create_inbox_item_for_course_request,
    create_inbox_item_for_course_request_outcome,
    resolve_inbox_items_for_delivery_request,
)


class CourseDeliveryRequestError(ValidationError):
    pass


def instructor_can_request_course(instructor: Personnel, course_type: CourseType) -> bool:
    if instructor.deliverable_course_types.filter(pk=course_type.pk).exists():
        return False
    if InstructorCourseRequest.objects.filter(
        instructor=instructor,
        course_type=course_type,
        status=InstructorCourseRequestStatus.PENDING,
    ).exists():
        return False
    return True


@transaction.atomic
def create_course_delivery_request(
    instructor: Personnel,
    course_type: CourseType,
    *,
    message: str = "",
) -> InstructorCourseRequest:
    if course_type.is_suspended:
        raise CourseDeliveryRequestError("That course type is not available.")
    if instructor.deliverable_course_types.filter(pk=course_type.pk).exists():
        raise CourseDeliveryRequestError("You are already approved to deliver this course.")
    if InstructorCourseRequest.objects.filter(
        instructor=instructor,
        course_type=course_type,
        status=InstructorCourseRequestStatus.PENDING,
    ).exists():
        raise CourseDeliveryRequestError("You already have a pending request for this course.")

    request = InstructorCourseRequest.objects.create(
        instructor=instructor,
        course_type=course_type,
        message=(message or "").strip(),
    )
    create_inbox_item_for_course_request(request)
    return request


@transaction.atomic
def approve_course_delivery_request(request: InstructorCourseRequest, *, admin_user, admin_note: str = "") -> None:
    if request.status != InstructorCourseRequestStatus.PENDING:
        raise CourseDeliveryRequestError("This request is no longer pending.")

    request.status = InstructorCourseRequestStatus.APPROVED
    request.resolved_at = timezone.now()
    request.resolved_by = admin_user
    request.admin_note = (admin_note or "").strip()
    request.save(update_fields=["status", "resolved_at", "resolved_by", "admin_note"])

    request.instructor.deliverable_course_types.add(request.course_type)

    resolve_inbox_items_for_delivery_request(request, user=admin_user)
    create_inbox_item_for_course_request_outcome(request, approved=True)


@transaction.atomic
def decline_course_delivery_request(request: InstructorCourseRequest, *, admin_user, admin_note: str = "") -> None:
    if request.status != InstructorCourseRequestStatus.PENDING:
        raise CourseDeliveryRequestError("This request is no longer pending.")

    request.status = InstructorCourseRequestStatus.DECLINED
    request.resolved_at = timezone.now()
    request.resolved_by = admin_user
    request.admin_note = (admin_note or "").strip()
    request.save(update_fields=["status", "resolved_at", "resolved_by", "admin_note"])

    resolve_inbox_items_for_delivery_request(request, user=admin_user)
    create_inbox_item_for_course_request_outcome(request, approved=False)

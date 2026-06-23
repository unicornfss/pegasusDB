"""Unified personnel inbox — create, read, and resolve notifications."""

from __future__ import annotations

from django.contrib.auth.models import Group
from django.db.models import Q
from django.utils import timezone

from ..models import (
    CourseSwap,
    CourseSwapStatus,
    InstructorCourseRequest,
    Personnel,
    StaffInboxItem,
    StaffInboxItemKind,
    StaffInboxItemStatus,
)
from ..utils.user_roles import user_has_role


def admin_personnel_queryset():
    return (
        Personnel.objects.filter(
            is_active=True,
            user__is_active=True,
            user__groups__name__iexact="admin",
        )
        .select_related("user")
        .distinct()
    )


def inbox_items_for_personnel(personnel, *, status: str = "open", scope: str = "staff"):
    """
    scope:
      staff  — instructor messages (course swaps)
      admin  — admin workflow (course delivery requests)
    """
    qs = StaffInboxItem.objects.select_related(
        "course_delivery_request__instructor",
        "course_delivery_request__course_type",
        "course_swap__booking",
        "course_swap__booking__course_type",
        "course_swap__from_instructor",
        "course_swap__to_instructor",
        "resolved_by",
    )
    if scope == "admin":
        qs = qs.filter(
            Q(recipient=personnel, kind=StaffInboxItemKind.COURSE_DELIVERY_REQUEST)
            | Q(
                recipient__isnull=True,
                kind=StaffInboxItemKind.COURSE_DELIVERY_REQUEST,
            )
        )
    else:
        qs = qs.filter(
            recipient=personnel,
            kind__in=(
                StaffInboxItemKind.COURSE_SWAP_INCOMING,
                StaffInboxItemKind.COURSE_SWAP_OUTCOME,
                StaffInboxItemKind.COURSE_DELIVERY_OUTCOME,
            ),
        )
    if status == "resolved":
        return qs.filter(
            Q(status=StaffInboxItemStatus.RESOLVED) | Q(read_at__isnull=False)
        )
    return qs.filter(
        status=StaffInboxItemStatus.OPEN,
        read_at__isnull=True,
    )


def unread_inbox_count(personnel, *, scope: str | None = None) -> int:
    if not personnel:
        return 0
    counts = unread_inbox_counts(personnel)
    if scope == "staff":
        return counts["staff"]
    if scope == "admin":
        return counts["admin"]
    return counts["total"]


def unread_inbox_counts(personnel) -> dict[str, int]:
    """Return staff/admin/total unread counts with at most two lightweight queries."""
    empty = {"staff": 0, "admin": 0, "total": 0}
    if not personnel:
        return empty

    open_filter = {
        "status": StaffInboxItemStatus.OPEN,
        "read_at__isnull": True,
    }
    staff = StaffInboxItem.objects.filter(
        recipient=personnel,
        kind__in=(
            StaffInboxItemKind.COURSE_SWAP_INCOMING,
            StaffInboxItemKind.COURSE_SWAP_OUTCOME,
            StaffInboxItemKind.COURSE_DELIVERY_OUTCOME,
        ),
        **open_filter,
    ).count()
    admin = StaffInboxItem.objects.filter(
        Q(recipient=personnel, kind=StaffInboxItemKind.COURSE_DELIVERY_REQUEST)
        | Q(
            recipient__isnull=True,
            kind=StaffInboxItemKind.COURSE_DELIVERY_REQUEST,
        ),
        **open_filter,
    ).count()
    return {"staff": staff, "admin": admin, "total": staff + admin}


def mark_inbox_items_read(personnel, *, scope: str = "staff", item_ids=None) -> int:
    if not personnel:
        return 0
    qs = inbox_items_for_personnel(personnel, status="open", scope=scope)
    if item_ids is not None:
        qs = qs.filter(pk__in=item_ids)
    pks = list(qs.values_list("pk", flat=True))
    if not pks:
        return 0

    now = timezone.now()
    count = StaffInboxItem.objects.filter(pk__in=pks).update(read_at=now)

    informational_kinds = (
        StaffInboxItemKind.COURSE_SWAP_OUTCOME,
        StaffInboxItemKind.COURSE_DELIVERY_OUTCOME,
    )
    StaffInboxItem.objects.filter(
        pk__in=pks,
        kind__in=informational_kinds,
    ).update(
        status=StaffInboxItemStatus.RESOLVED,
        resolved_at=now,
    )

    if scope == "staff":
        from .course_swaps import mark_swap_outcomes_seen

        mark_swap_outcomes_seen(personnel)
    if count:
        from .inbox_push import notify_personnel

        notify_personnel(personnel)
    return count


def resolve_inbox_item(item: StaffInboxItem, *, user) -> None:
    item.status = StaffInboxItemStatus.RESOLVED
    item.resolved_at = timezone.now()
    item.resolved_by = user
    if not item.read_at:
        item.read_at = item.resolved_at
    item.save(update_fields=["status", "resolved_at", "resolved_by", "read_at"])


def resolve_inbox_items_for_delivery_request(request: InstructorCourseRequest, *, user) -> None:
    for item in request.inbox_items.filter(status=StaffInboxItemStatus.OPEN):
        resolve_inbox_item(item, user=user)


def resolve_inbox_items_for_swap(swap: CourseSwap, *, kinds, user=None) -> None:
    qs = swap.inbox_items.filter(status=StaffInboxItemStatus.OPEN, kind__in=kinds)
    now = timezone.now()
    for item in qs:
        item.status = StaffInboxItemStatus.RESOLVED
        item.resolved_at = now
        if user:
            item.resolved_by = user
        if not item.read_at:
            item.read_at = now
        item.save(update_fields=["status", "resolved_at", "resolved_by", "read_at"])


def create_inbox_item_for_course_request(request: InstructorCourseRequest) -> list[StaffInboxItem]:
    summary = (
        f"{request.instructor.name} requested approval to deliver "
        f"{request.course_type.name}"
    )
    admins = list(admin_personnel_queryset())
    recipients = admins or [None]
    created = []
    for admin in recipients:
        created.append(
            StaffInboxItem.objects.create(
                recipient=admin,
                kind=StaffInboxItemKind.COURSE_DELIVERY_REQUEST,
                status=StaffInboxItemStatus.OPEN,
                summary=summary,
                course_delivery_request=request,
            )
        )
    from .inbox_push import notify_personnel

    for admin in admins:
        notify_personnel(admin)
    return created


def create_inbox_item_for_course_request_outcome(
    request: InstructorCourseRequest, *, approved: bool
) -> StaffInboxItem:
    verb = "approved" if approved else "declined"
    summary = f"Your request to deliver {request.course_type.name} was {verb}"
    item = StaffInboxItem.objects.create(
        recipient=request.instructor,
        kind=StaffInboxItemKind.COURSE_DELIVERY_OUTCOME,
        status=StaffInboxItemStatus.OPEN,
        summary=summary,
        course_delivery_request=request,
    )
    from .inbox_push import notify_personnel

    notify_personnel(request.instructor)
    return item


def _swap_summary_line(swap: CourseSwap) -> str:
    booking = swap.booking
    ref = booking.course_reference or str(booking.id)
    course = getattr(booking.course_type, "name", "Course")
    date = booking.course_date.strftime("%d %b %Y") if booking.course_date else "—"
    return f"{ref} · {course} · {date}"


def create_inbox_item_for_swap_offer(swap: CourseSwap) -> StaffInboxItem:
    summary = (
        f"{swap.from_instructor.name} offered you a course cover: "
        f"{_swap_summary_line(swap)}"
    )
    item = StaffInboxItem.objects.create(
        recipient=swap.to_instructor,
        kind=StaffInboxItemKind.COURSE_SWAP_INCOMING,
        status=StaffInboxItemStatus.OPEN,
        summary=summary,
        course_swap=swap,
    )
    from .inbox_push import notify_personnel

    notify_personnel(swap.to_instructor)
    return item


def create_inbox_item_for_swap_outcome(swap: CourseSwap, *, accepted: bool) -> StaffInboxItem:
    verb = "accepted" if accepted else "declined"
    summary = (
        f"{swap.to_instructor.name} {verb} your course cover offer: "
        f"{_swap_summary_line(swap)}"
    )
    item = StaffInboxItem.objects.create(
        recipient=swap.from_instructor,
        kind=StaffInboxItemKind.COURSE_SWAP_OUTCOME,
        status=StaffInboxItemStatus.OPEN,
        summary=summary,
        course_swap=swap,
    )
    from .inbox_push import notify_personnel

    notify_personnel(swap.from_instructor)
    return item


def user_can_act_on_inbox_item(user, item: StaffInboxItem) -> bool:
    personnel = getattr(user, "personnel", None)
    if not personnel:
        return False
    if (
        item.kind == StaffInboxItemKind.COURSE_DELIVERY_REQUEST
        and user_has_role(user, "admin")
    ):
        return True
    if item.recipient_id and item.recipient_id != personnel.pk:
        return False
    if item.recipient_id is None and not user_has_role(user, "admin"):
        return False
    return True

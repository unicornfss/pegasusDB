from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Booking, CourseSwap, CourseSwapStatus
from .services.course_swaps import (
    CourseSwapError,
    accept_swap,
    cancel_swap,
    create_swap_request,
    decline_swap,
    eligible_target_instructors,
    mark_swap_outcomes_seen,
    swappable_bookings_for_instructor,
    unread_outcome_swaps,
)
from .views_instructor import _get_instructor


def _require_instructor(request):
    inst = _get_instructor(request.user)
    if not inst:
        messages.error(request, "Your user account isn't linked to an instructor record.")
        return None
    return inst


def _swap_queryset():
    return CourseSwap.objects.select_related(
        "booking",
        "booking__course_type",
        "booking__business",
        "booking__training_location",
        "from_instructor",
        "to_instructor",
    )


@login_required
def instructor_course_swaps(request):
    inst = _require_instructor(request)
    if not inst:
        return redirect("home")

    incoming = list(
        _swap_queryset()
        .filter(to_instructor=inst, status=CourseSwapStatus.PENDING)
        .order_by("created_at")
    )
    outgoing = list(
        _swap_queryset()
        .filter(from_instructor=inst, status=CourseSwapStatus.PENDING)
        .order_by("-created_at")
    )
    swappable_bookings = list(swappable_bookings_for_instructor(inst))
    target_instructors = list(eligible_target_instructors(exclude_personnel=inst))

    recent = list(
        _swap_queryset()
        .filter(Q(from_instructor=inst) | Q(to_instructor=inst))
        .exclude(status=CourseSwapStatus.PENDING)
        .order_by("-responded_at", "-created_at")[:25]
    )

    new_outcomes = unread_outcome_swaps(inst)
    new_outcome_ids = {swap.id for swap in new_outcomes}
    mark_swap_outcomes_seen(inst)

    return render(
        request,
        "instructor/course_swaps.html",
        {
            "title": "Course swaps",
            "instructor": inst,
            "incoming": incoming,
            "outgoing": outgoing,
            "swappable_bookings": swappable_bookings,
            "target_instructors": target_instructors,
            "recent": recent,
            "incoming_count": len(incoming),
            "new_outcomes": new_outcomes,
            "new_outcome_ids": new_outcome_ids,
        },
    )


@login_required
@require_POST
def instructor_course_swap_request(request):
    inst = _require_instructor(request)
    if not inst:
        return redirect("home")

    booking = get_object_or_404(Booking, pk=request.POST.get("booking_id"))
    to_instructor = get_object_or_404(
        eligible_target_instructors(exclude_personnel=inst),
        pk=request.POST.get("to_instructor_id"),
    )
    message = (request.POST.get("message") or "").strip()

    try:
        create_swap_request(
            booking=booking,
            from_instructor=inst,
            to_instructor=to_instructor,
            message=message,
        )
        messages.success(
            request,
            f"Cover request sent to {to_instructor.name}. They must accept before the course transfers.",
        )
    except CourseSwapError as exc:
        messages.error(request, str(exc))

    return redirect(reverse("instructor_course_swaps") + "#request-cover")


@login_required
@require_POST
def instructor_course_swap_accept(request, pk):
    inst = _require_instructor(request)
    if not inst:
        return redirect("home")

    try:
        swap = accept_swap(swap_id=pk, recipient=inst)
        messages.success(
            request,
            f"You accepted the course swap. {swap.booking.course_reference or 'The booking'} is now assigned to you.",
        )
    except CourseSwapError as exc:
        messages.error(request, str(exc))

    return redirect(reverse("instructor_course_swaps") + "#incoming")


@login_required
@require_POST
def instructor_course_swap_decline(request, pk):
    inst = _require_instructor(request)
    if not inst:
        return redirect("home")

    try:
        swap = decline_swap(swap_id=pk, recipient=inst)
        messages.info(request, f"You declined the swap for {swap.booking.course_reference or 'that booking'}.")
    except CourseSwapError as exc:
        messages.error(request, str(exc))

    return redirect(reverse("instructor_course_swaps") + "#incoming")


@login_required
@require_POST
def instructor_course_swap_cancel(request, pk):
    inst = _require_instructor(request)
    if not inst:
        return redirect("home")

    try:
        swap = cancel_swap(swap_id=pk, offerer=inst)
        messages.info(request, f"Cover request cancelled for {swap.booking.course_reference or 'that booking'}.")
    except CourseSwapError as exc:
        messages.error(request, str(exc))

    return redirect(reverse("instructor_course_swaps") + "#outgoing")

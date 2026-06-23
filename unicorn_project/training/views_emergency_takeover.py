from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Booking
from .services.emergency_takeover import (
    EmergencyTakeoverError,
    bookings_available_for_takeover,
    execute_emergency_takeover,
)
from .views_instructor import _get_instructor


def _require_instructor(request):
    inst = _get_instructor(request.user)
    if not inst:
        messages.error(request, "Your user account isn't linked to an instructor record.")
        return None
    return inst


@login_required
def instructor_emergency_takeover(request):
    inst = _require_instructor(request)
    if not inst:
        return redirect("home")

    target_date = timezone.localdate()
    rows = bookings_available_for_takeover(target_date, inst)

    return render(
        request,
        "instructor/emergency_takeover.html",
        {
            "title": "Emergency course takeover",
            "instructor": inst,
            "target_date": target_date,
            "rows": rows,
        },
    )


@login_required
@require_POST
def instructor_emergency_takeover_confirm(request, pk):
    inst = _require_instructor(request)
    if not inst:
        return redirect("home")

    booking = get_object_or_404(Booking, pk=pk)
    day_ids = request.POST.getlist("day_ids")
    note = (request.POST.get("note") or "").strip()

    try:
        takeover = execute_emergency_takeover(
            booking=booking,
            taker=inst,
            day_ids=day_ids,
            note=note,
        )
    except EmergencyTakeoverError as exc:
        messages.error(request, str(exc))
        return redirect("instructor_emergency_takeover")

    ref = booking.course_reference or str(booking.pk)
    if takeover.is_full_takeover:
        messages.success(
            request,
            f"You have taken over the full course {ref}. "
            f"Fee £{takeover.fee_amount} has been assigned to you.",
        )
        return redirect("instructor_booking_detail", pk=booking.pk)

    day_count = takeover.days.count()
    messages.success(
        request,
        f"Emergency cover recorded for {ref} "
        f"({day_count} day{'s' if day_count != 1 else ''}, fee £{takeover.fee_amount}).",
    )
    return redirect("instructor_booking_detail", pk=booking.pk)

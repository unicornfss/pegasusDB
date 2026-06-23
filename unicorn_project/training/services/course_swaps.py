from django.db import transaction
from django.utils import timezone

from ..forms import delivery_personnel_queryset
from ..models import Booking, BookingDay, CourseSwap, CourseSwapStatus, Invoice


SWAPPABLE_BOOKING_STATUSES = ("scheduled", "in_progress")


class CourseSwapError(Exception):
    pass


def swappable_bookings_for_instructor(instructor):
    pending_booking_ids = CourseSwap.objects.filter(
        status=CourseSwapStatus.PENDING,
    ).values_list("booking_id", flat=True)

    return (
        Booking.objects.filter(
            instructor=instructor,
            status__in=SWAPPABLE_BOOKING_STATUSES,
        )
        .exclude(business__is_dummy=True)
        .exclude(pk__in=pending_booking_ids)
        .select_related("course_type", "business", "training_location")
        .prefetch_related("days")
        .order_by("course_date", "start_time", "id")
    )


def eligible_target_instructors(exclude_personnel=None):
    qs = delivery_personnel_queryset()
    if exclude_personnel:
        qs = qs.exclude(pk=exclude_personnel.pk)
    return qs


def _validate_swap_parties(booking, from_instructor, to_instructor):
    if not booking or not from_instructor or not to_instructor:
        raise CourseSwapError("Invalid swap request.")
    if from_instructor.pk == to_instructor.pk:
        raise CourseSwapError("You cannot offer a swap to yourself.")
    if booking.instructor_id != from_instructor.pk:
        raise CourseSwapError("You can only offer swaps for your own bookings.")
    if booking.status not in SWAPPABLE_BOOKING_STATUSES:
        raise CourseSwapError("This booking cannot be swapped in its current state.")
    if getattr(booking.business, "is_dummy", False):
        raise CourseSwapError("Practice bookings cannot be swapped.")
    if not eligible_target_instructors(exclude_personnel=from_instructor).filter(pk=to_instructor.pk).exists():
        raise CourseSwapError("The selected instructor is not available for course swaps.")
    if CourseSwap.objects.filter(booking=booking, status=CourseSwapStatus.PENDING).exists():
        raise CourseSwapError("This booking already has a pending swap request.")


def create_swap_request(*, booking, from_instructor, to_instructor, message=""):
    _validate_swap_parties(booking, from_instructor, to_instructor)
    swap = CourseSwap.objects.create(
        booking=booking,
        from_instructor=from_instructor,
        to_instructor=to_instructor,
        message=(message or "").strip(),
    )
    swap.booking = booking
    notify_swap_offer(swap)
    return swap


def _get_pending_swap_for_user(swap_id, user_personnel, *, as_recipient=False, as_offerer=False):
    swap = (
        CourseSwap.objects.select_related(
            "booking",
            "booking__course_type",
            "booking__business",
            "from_instructor",
            "to_instructor",
        )
        .filter(pk=swap_id, status=CourseSwapStatus.PENDING)
        .first()
    )
    if not swap:
        raise CourseSwapError("Swap request not found or no longer pending.")
    if as_recipient and swap.to_instructor_id != user_personnel.pk:
        raise CourseSwapError("You are not the recipient of this swap request.")
    if as_offerer and swap.from_instructor_id != user_personnel.pk:
        raise CourseSwapError("You did not create this swap request.")
    return swap


@transaction.atomic
def accept_swap(*, swap_id, recipient):
    swap = _get_pending_swap_for_user(swap_id, recipient, as_recipient=True)
    booking = swap.booking

    if booking.instructor_id != swap.from_instructor_id:
        raise CourseSwapError("This booking is no longer assigned to the offering instructor.")

    booking.instructor = swap.to_instructor
    booking.save(update_fields=["instructor"])

    BookingDay.objects.filter(booking=booking).update(instructor=swap.to_instructor)

    invoice = booking.invoices.filter(instructor_id=swap.from_instructor_id).first()
    if invoice and invoice.status in ("draft", "awaiting_review"):
        invoice.instructor = swap.to_instructor
        invoice.account_name = (swap.to_instructor.name_on_account or "").strip()
        invoice.sort_code = (swap.to_instructor.bank_sort_code or "").strip()
        invoice.account_number = (swap.to_instructor.bank_account_number or "").strip()
        invoice.save(update_fields=["instructor", "account_name", "sort_code", "account_number"])

    swap.status = CourseSwapStatus.ACCEPTED
    swap.responded_at = timezone.now()
    swap.save(update_fields=["status", "responded_at"])

    notify_swap_accepted(swap)
    return swap


def decline_swap(*, swap_id, recipient):
    swap = _get_pending_swap_for_user(swap_id, recipient, as_recipient=True)
    swap.status = CourseSwapStatus.DECLINED
    swap.responded_at = timezone.now()
    swap.save(update_fields=["status", "responded_at"])
    notify_swap_declined(swap)
    return swap


def cancel_swap(*, swap_id, offerer):
    swap = _get_pending_swap_for_user(swap_id, offerer, as_offerer=True)
    swap.status = CourseSwapStatus.CANCELLED
    swap.responded_at = timezone.now()
    swap.save(update_fields=["status", "responded_at"])
    from ..models import StaffInboxItemKind
    from .staff_inbox import resolve_inbox_items_for_swap

    resolve_inbox_items_for_swap(
        swap,
        kinds=[StaffInboxItemKind.COURSE_SWAP_INCOMING],
    )
    return swap


def _booking_summary_line(booking):
    ref = booking.course_reference or str(booking.id)
    date = booking.course_date.strftime("%d %b %Y") if booking.course_date else "—"
    return f"{ref} · {booking.course_type.name} · {date}"


def notify_swap_offer(swap):
    from ..utils.telegram_course_swaps import send_cover_request_telegram
    from .staff_inbox import create_inbox_item_for_swap_offer

    create_inbox_item_for_swap_offer(swap)
    send_cover_request_telegram(swap)


def notify_swap_accepted(swap):
    from ..utils.booking_notifications import notify_new_booking
    from ..utils.telegram_course_swaps import send_cover_outcome_telegram_to_offerer
    from ..models import StaffInboxItemKind
    from .staff_inbox import (
        create_inbox_item_for_swap_outcome,
        resolve_inbox_items_for_swap,
    )

    resolve_inbox_items_for_swap(
        swap,
        kinds=[StaffInboxItemKind.COURSE_SWAP_INCOMING],
    )
    create_inbox_item_for_swap_outcome(swap, accepted=True)
    notify_new_booking(swap.booking)
    send_cover_outcome_telegram_to_offerer(swap, accepted=True)


def notify_swap_declined(swap):
    from ..utils.telegram_course_swaps import send_cover_outcome_telegram_to_offerer
    from ..models import StaffInboxItemKind
    from .staff_inbox import (
        create_inbox_item_for_swap_outcome,
        resolve_inbox_items_for_swap,
    )

    resolve_inbox_items_for_swap(
        swap,
        kinds=[StaffInboxItemKind.COURSE_SWAP_INCOMING],
    )
    create_inbox_item_for_swap_outcome(swap, accepted=False)
    send_cover_outcome_telegram_to_offerer(swap, accepted=False)


OUTCOME_STATUSES = (CourseSwapStatus.ACCEPTED, CourseSwapStatus.DECLINED)


def menu_badge_counts(personnel):
    """Counts for the instructor sidebar Course swaps badge."""
    if not personnel:
        return {
            "course_swap_menu_badge_count": 0,
            "course_swap_incoming_count": 0,
            "course_swap_outcome_count": 0,
        }

    incoming_count = CourseSwap.objects.filter(
        to_instructor=personnel,
        status=CourseSwapStatus.PENDING,
    ).count()

    outcome_count = CourseSwap.objects.filter(
        from_instructor=personnel,
        status__in=OUTCOME_STATUSES,
        from_instructor_seen_at__isnull=True,
    ).count()

    return {
        "course_swap_menu_badge_count": incoming_count + outcome_count,
        "course_swap_incoming_count": incoming_count,
        "course_swap_outcome_count": outcome_count,
    }


def unread_outcome_swaps(personnel):
    return list(
        CourseSwap.objects.filter(
            from_instructor=personnel,
            status__in=OUTCOME_STATUSES,
            from_instructor_seen_at__isnull=True,
        )
        .select_related("booking", "booking__course_type", "to_instructor")
        .order_by("-responded_at", "-created_at")
    )


def mark_swap_outcomes_seen(personnel):
    """Clear accept/decline update badges once the offerer opens Course swaps."""
    CourseSwap.objects.filter(
        from_instructor=personnel,
        status__in=OUTCOME_STATUSES,
        from_instructor_seen_at__isnull=True,
    ).update(from_instructor_seen_at=timezone.now())

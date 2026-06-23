from django.db.models import Exists, OuterRef, Q

from ..models import Booking, BookingDay, Invoice


def booking_has_invoice_for(personnel, *, statuses=None):
    """Exists subquery: booking has an invoice assigned to this instructor."""
    if not personnel:
        return Exists(Invoice.objects.none())
    qs = Invoice.objects.filter(
        booking_id=OuterRef("pk"),
        instructor_id=personnel.pk,
    )
    if statuses is not None:
        qs = qs.filter(status__in=statuses)
    return Exists(qs)


def instructor_visible_booking_ids(personnel) -> list:
    """
    Booking IDs this instructor should see, without expensive JOIN + DISTINCT.
    """
    if not personnel:
        return []

    ids: list = []
    seen: set = set()

    for pk in Booking.objects.filter(instructor_id=personnel.pk).values_list("pk", flat=True):
        ids.append(pk)
        seen.add(pk)

    for pk in (
        BookingDay.objects.filter(instructor_id=personnel.pk)
        .exclude(booking_id__in=seen)
        .values_list("booking_id", flat=True)
        .distinct()
    ):
        ids.append(pk)
        seen.add(pk)

    for pk in (
        Invoice.objects.filter(instructor_id=personnel.pk)
        .exclude(booking_id__in=seen)
        .values_list("booking_id", flat=True)
        .distinct()
    ):
        ids.append(pk)

    return ids


def instructor_bookings_queryset(personnel):
    """Bookings visible on the instructor dashboard."""
    booking_ids = instructor_visible_booking_ids(personnel)
    if not booking_ids:
        return Booking.objects.none()
    return Booking.objects.filter(pk__in=booking_ids)


def effective_day_instructor_id(day):
    """Instructor assigned to deliver a specific day (falls back to booking lead)."""
    if day.instructor_id:
        return day.instructor_id
    booking = getattr(day, "booking", None)
    if booking and booking.instructor_id:
        return booking.instructor_id
    return None


def instructor_can_access_booking(personnel, booking):
    """Whether this instructor may open and work on the booking."""
    if not personnel or not booking:
        return False
    if booking.instructor_id == personnel.pk:
        return True
    if booking.days.filter(instructor_id=personnel.pk).exists():
        return True
    if Invoice.objects.filter(booking_id=booking.pk, instructor_id=personnel.pk).exists():
        return True
    return False


def instructor_can_access_day(personnel, day):
    """Whether this instructor may manage a specific course day."""
    if not personnel or not day:
        return False
    booking = day.booking
    if booking.instructor_id == personnel.pk:
        return True
    if day.instructor_id == personnel.pk:
        return True
    return False


def lead_invoice_status_map(bookings, *, instructor_id=None):
    """
    Map booking_id -> invoice status for a page of bookings (at most one query).
    Prefers the lead instructor's invoice; falls back to instructor_id when given.
    """
    booking_list = list(bookings)
    if not booking_list:
        return {}

    booking_ids = [b.pk for b in booking_list]
    preferred_by_booking = {
        b.pk: instructor_id if instructor_id is not None else b.instructor_id
        for b in booking_list
    }

    grouped: dict = {}
    for inv in Invoice.objects.filter(booking_id__in=booking_ids).only(
        "booking_id", "instructor_id", "status"
    ):
        grouped.setdefault(inv.booking_id, []).append(inv)

    result: dict = {}
    for bid, invs in grouped.items():
        preferred = preferred_by_booking.get(bid)
        chosen = next(
            (inv for inv in invs if preferred and inv.instructor_id == preferred),
            invs[0],
        )
        result[bid] = (chosen.status or "").lower()
    return result

from django.db.models import Exists, OuterRef, Q

from ..models import Booking, Invoice


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


def instructor_bookings_queryset(personnel):
    """Bookings visible on the instructor dashboard."""
    if not personnel:
        return Booking.objects.none()

    return (
        Booking.objects.filter(
            Q(instructor=personnel)
            | Q(days__instructor=personnel)
            | booking_has_invoice_for(personnel)
        )
        .distinct()
    )

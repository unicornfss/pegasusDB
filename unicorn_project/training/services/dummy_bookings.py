from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..models import Booking, DelegateRegister, FeedbackResponse, ExamAttempt


@transaction.atomic
def delete_dummy_booking_tree(booking: Booking) -> None:
    if not booking.is_dummy_business:
        raise ValueError("Deep dummy deletion is only supported for dummy businesses.")

    DelegateRegister.objects.filter(booking_day__booking=booking).delete()
    FeedbackResponse.objects.filter(booking=booking).delete()
    ExamAttempt.objects.filter(booking=booking).delete()

    invoice = getattr(booking, "invoice", None)
    if invoice is not None:
        invoice.delete()

    booking.days.all().delete()
    booking.delete()


def purge_expired_dummy_bookings(*, max_age_days: int = 7) -> int:
    cutoff = timezone.now() - timedelta(days=max_age_days)
    bookings = list(
        Booking.objects
        .select_related("business")
        .filter(business__is_dummy=True, created_at__lte=cutoff)
        .order_by("created_at")
    )

    deleted = 0
    for booking in bookings:
        delete_dummy_booking_tree(booking)
        deleted += 1

    return deleted
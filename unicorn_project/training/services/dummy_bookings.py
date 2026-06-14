from datetime import timedelta

from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ..models import Booking, BookingDay, DelegateRegister, FeedbackResponse, ExamAttempt
from ..utils.user_roles import user_has_role


def is_dual_admin_instructor(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and user_has_role(user, "admin")
        and user_has_role(user, "instructor")
        and getattr(user, "personnel", None) is not None
    )


def admin_may_view_booking(user, booking: Booking) -> bool:
    """Pure admins cannot see practice bookings; dual-role admins see their own only."""
    if not getattr(booking, "is_dummy_business", False):
        return True
    if not is_dual_admin_instructor(user):
        return False
    return booking.instructor_id == user.personnel.pk


def filter_bookings_visible_to_admin(user, queryset: QuerySet) -> QuerySet:
    if is_dual_admin_instructor(user):
        personnel = user.personnel
        return queryset.filter(
            Q(business__is_dummy=False)
            | Q(business__is_dummy=True, instructor=personnel)
        )
    return queryset.exclude(business__is_dummy=True)


def filter_delegate_registers_visible_to_admin(user, queryset: QuerySet) -> QuerySet:
    visible_bookings = filter_bookings_visible_to_admin(user, Booking.objects.all())
    return queryset.filter(booking_day__booking__in=visible_bookings)


def get_admin_booking_or_404(user, pk, queryset=None) -> Booking:
    qs = queryset if queryset is not None else Booking.objects.select_related("business")
    booking = get_object_or_404(qs, pk=pk)
    if not admin_may_view_booking(user, booking):
        raise Http404("Booking not found.")
    return booking


def get_admin_booking_day_or_404(user, pk, queryset=None) -> BookingDay:
    qs = queryset if queryset is not None else BookingDay.objects.select_related(
        "booking", "booking__business"
    )
    day = get_object_or_404(qs, pk=pk)
    if not admin_may_view_booking(user, day.booking):
        raise Http404("Booking day not found.")
    return day


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
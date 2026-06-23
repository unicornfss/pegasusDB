from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from ..models import (
    Booking,
    BookingDay,
    CourseSwap,
    CourseSwapStatus,
    EmergencyTakeover,
    Invoice,
    InvoiceItem,
)
from ..utils.instructor_access import effective_day_instructor_id


TAKEOVER_BOOKING_STATUSES = ("scheduled", "in_progress")


class EmergencyTakeoverError(Exception):
    pass


def _money(value):
    return Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _can_deliver_course(personnel, course_type):
    if not personnel or not course_type:
        return False
    return personnel.deliverable_course_types.filter(pk=course_type.pk).exists()


def _booking_days_ordered(booking):
    return list(booking.days.order_by("date", "id"))


def _takeover_row_for_booking(booking, target_date, taker):
    days = _booking_days_ordered(booking)
    if not days:
        return None

    today_day = next((d for d in days if d.date == target_date), None)
    if not today_day:
        return None

    today_instructor_id = effective_day_instructor_id(today_day)
    if today_instructor_id == taker.pk:
        return None

    if CourseSwap.objects.filter(booking=booking, status=CourseSwapStatus.PENDING).exists():
        return None

    total_days = len(days)
    total_fee = _money(booking.instructor_fee)
    per_day_fee = (
        (total_fee / Decimal(total_days)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total_days
        else total_fee
    )

    future_days = [d for d in days if d.date >= target_date and effective_day_instructor_id(d) != taker.pk]
    selectable_days = []
    for day in future_days:
        eff_id = effective_day_instructor_id(day)
        selectable_days.append(
            {
                "day": day,
                "date": day.date,
                "is_today": day.date == target_date,
                "current_instructor_id": eff_id,
            }
        )

    if not selectable_days:
        return None

    is_single_day_course = total_days <= 1
    lead_instructor = booking.instructor

    return {
        "booking": booking,
        "today_day": today_day,
        "lead_instructor": lead_instructor,
        "today_instructor_id": today_instructor_id,
        "total_days": total_days,
        "total_fee": total_fee,
        "per_day_fee": per_day_fee,
        "selectable_days": selectable_days,
        "is_single_day_course": is_single_day_course,
        "default_day_ids": [d["day"].pk for d in selectable_days if d["is_today"]]
        if not is_single_day_course
        else [d["day"].pk for d in selectable_days],
    }


def bookings_available_for_takeover(target_date, taker):
    if not taker:
        return []

    qs = (
        Booking.objects.filter(
            status__in=TAKEOVER_BOOKING_STATUSES,
            days__date=target_date,
        )
        .exclude(business__is_dummy=True)
        .select_related(
            "course_type",
            "business",
            "training_location",
            "instructor",
        )
        .prefetch_related("days", "days__instructor")
        .distinct()
        .order_by("course_date", "start_time", "id")
    )

    rows = []
    for booking in qs:
        if not _can_deliver_course(taker, booking.course_type):
            continue
        row = _takeover_row_for_booking(booking, target_date, taker)
        if row:
            rows.append(row)
    return rows


def _transfer_invoice_to_instructor(invoice, new_instructor):
    if not invoice or invoice.status not in ("draft", "awaiting_review"):
        return
    invoice.instructor = new_instructor
    invoice.base_fee_override = None
    invoice.account_name = (new_instructor.name_on_account or "").strip()
    invoice.sort_code = (new_instructor.bank_sort_code or "").strip()
    invoice.account_number = (new_instructor.bank_account_number or "").strip()
    invoice.save(
        update_fields=[
            "instructor",
            "base_fee_override",
            "account_name",
            "sort_code",
            "account_number",
        ]
    )


def _get_or_create_cover_invoice(booking, cover_instructor, base_fee):
    inv = booking.invoice_for(cover_instructor)
    if inv:
        inv.base_fee_override = _money((inv.base_fee_override or 0) + base_fee)
        inv.save(update_fields=["base_fee_override"])
        return inv

    return Invoice.objects.create(
        booking=booking,
        instructor=cover_instructor,
        base_fee_override=_money(base_fee),
        account_name=(cover_instructor.name_on_account or "").strip(),
        sort_code=(cover_instructor.bank_sort_code or "").strip(),
        account_number=(cover_instructor.bank_account_number or "").strip(),
        status="draft",
    )


def _append_booking_note(booking, text):
    note = (text or "").strip()
    if not note:
        return
    existing = (booking.booking_notes or "").strip()
    booking.booking_notes = f"{existing}\n\n{note}".strip() if existing else note


@transaction.atomic
def execute_emergency_takeover(*, booking, taker, day_ids, note=""):
    if not taker:
        raise EmergencyTakeoverError("You must be logged in as an instructor.")

    booking = (
        Booking.objects.select_related("course_type", "instructor", "business")
        .prefetch_related("days", "days__instructor")
        .filter(pk=booking.pk)
        .first()
    )
    if not booking:
        raise EmergencyTakeoverError("Booking not found.")

    if booking.status not in TAKEOVER_BOOKING_STATUSES:
        raise EmergencyTakeoverError("This booking cannot be taken over in its current state.")

    if getattr(booking.business, "is_dummy", False):
        raise EmergencyTakeoverError("Practice bookings cannot be taken over.")

    if not _can_deliver_course(taker, booking.course_type):
        raise EmergencyTakeoverError("You are not approved to deliver this course type.")

    if CourseSwap.objects.filter(booking=booking, status=CourseSwapStatus.PENDING).exists():
        raise EmergencyTakeoverError("This booking has a pending course swap request.")

    all_days = _booking_days_ordered(booking)
    if not all_days:
        raise EmergencyTakeoverError("This booking has no course days.")

    day_id_set = {int(x) for x in day_ids}
    selected_days = [d for d in all_days if d.pk in day_id_set]
    if not selected_days:
        raise EmergencyTakeoverError("Select at least one day to take over.")

    for day in selected_days:
        eff_id = effective_day_instructor_id(day)
        if eff_id == taker.pk:
            raise EmergencyTakeoverError(f"You are already assigned to {day.date.strftime('%d %b %Y')}.")

    total_days = len(all_days)
    is_full_takeover = total_days <= 1 or len(selected_days) == total_days

    original_instructor = booking.instructor
    existing_cover_total = _money(
        sum(
            (inv.base_fee_override or 0)
            for inv in booking.invoices.exclude(instructor_id=booking.instructor_id)
        )
    )
    total_fee_basis = _money(booking.instructor_fee) + existing_cover_total
    per_day_fee = (
        (total_fee_basis / Decimal(total_days)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total_days
        else total_fee_basis
    )
    cover_fee = _money(per_day_fee * Decimal(len(selected_days)))
    remaining_fee = _money(total_fee_basis - existing_cover_total - cover_fee)

    existing_cover_mileage = Decimal("0.00")
    cover_inv_existing = booking.invoice_for(taker)
    if cover_inv_existing:
        mile_item = cover_inv_existing.items.filter(
            description="Mileage (emergency cover, pro-rata)"
        ).first()
        if mile_item:
            existing_cover_mileage = _money(mile_item.amount)

    total_mileage_basis = Decimal("0.00")
    if booking.allow_mileage_claim and booking.mileage_fee:
        total_mileage_basis = _money(booking.mileage_fee) + existing_cover_mileage

    cover_mileage = Decimal("0.00")
    remaining_mileage = _money(booking.mileage_fee) if booking.allow_mileage_claim else Decimal("0.00")
    if total_mileage_basis:
        per_day_mileage = (
            (total_mileage_basis / Decimal(total_days)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if total_days
            else total_mileage_basis
        )
        cover_mileage = _money(per_day_mileage * Decimal(len(selected_days)))
        remaining_mileage = _money(total_mileage_basis - existing_cover_mileage - cover_mileage)

    if is_full_takeover:
        booking.instructor = taker
        booking.instructor_fee = total_fee_basis
        booking.save(update_fields=["instructor", "instructor_fee"])

        BookingDay.objects.filter(booking=booking).update(instructor=taker)

        lead_invoice = booking.invoices.filter(instructor_id=original_instructor.pk).first() if original_instructor else None
        if lead_invoice:
            _transfer_invoice_to_instructor(lead_invoice, taker)
        else:
            _get_or_create_cover_invoice(booking, taker, total_fee_basis)

        for other_inv in booking.invoices.exclude(instructor_id=taker.pk):
            if other_inv.status in ("draft", "awaiting_review"):
                other_inv.delete()

    else:
        for day in selected_days:
            day.instructor = taker
            day.save(update_fields=["instructor"])

        booking.instructor_fee = remaining_fee
        if booking.allow_mileage_claim and total_mileage_basis:
            booking.mileage_fee = remaining_mileage
            booking.save(update_fields=["instructor_fee", "mileage_fee"])
        else:
            booking.save(update_fields=["instructor_fee"])

        cover_inv = _get_or_create_cover_invoice(booking, taker, cover_fee)
        if cover_mileage > 0:
            mile_item, created = InvoiceItem.objects.get_or_create(
                invoice=cover_inv,
                description="Mileage (emergency cover, pro-rata)",
                defaults={"amount": cover_mileage},
            )
            if not created:
                mile_item.amount = _money(existing_cover_mileage + cover_mileage)
                mile_item.save(update_fields=["amount"])

        lead_invoice = booking.invoices.filter(instructor_id=original_instructor.pk).first() if original_instructor else None
        if lead_invoice and lead_invoice.status in ("draft", "awaiting_review"):
            lead_invoice.base_fee_override = None

    takeover = EmergencyTakeover.objects.create(
        booking=booking,
        taken_by=taker,
        replaced_instructor=original_instructor,
        fee_amount=cover_fee,
        mileage_amount=cover_mileage,
        is_full_takeover=is_full_takeover,
        note=(note or "").strip(),
    )
    takeover.days.set(selected_days)

    day_labels = ", ".join(d.date.strftime("%d %b %Y") for d in selected_days)
    ref = booking.course_reference or str(booking.pk)
    _append_booking_note(
        booking,
        (
            f"[Emergency cover {timezone.localdate().strftime('%d %b %Y')}] "
            f"{taker.name} took over {day_labels} on {ref}"
            f"{' (full course)' if is_full_takeover else ''}."
            f" Cover fee: £{cover_fee}."
        ),
    )
    booking.save(update_fields=["booking_notes"])

    from ..utils.booking_notifications import notify_new_booking

    notify_new_booking(booking)

    return takeover

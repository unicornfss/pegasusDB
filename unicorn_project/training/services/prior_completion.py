"""Detect delegates who previously passed the same course type."""
from __future__ import annotations

from django.db.models import Q

from ..models import DelegateRegister


def _identity_key(name, dob):
    name = (name or "").strip().lower()
    if not name or not dob:
        return None
    return (name, dob)


def prior_pass_dates_for_booking(booking, registers) -> dict[tuple, object]:
    """
    Map (name_lower, dob) -> most recent prior pass date for the same CourseType
    on a different booking.

    `registers` may be DelegateRegister instances or dict rows with an `obj` key.
    """
    if not booking or not booking.course_type_id:
        return {}

    keys = set()
    for item in registers or []:
        reg = item.get("obj") if isinstance(item, dict) else item
        if not reg:
            continue
        key = _identity_key(getattr(reg, "name", None), getattr(reg, "date_of_birth", None))
        if key:
            keys.add(key)

    if not keys:
        return {}

    q = Q()
    for name, dob in keys:
        q |= Q(name__iexact=name, date_of_birth=dob)

    rows = (
        DelegateRegister.objects.filter(
            q,
            outcome__iexact="pass",
            booking_day__booking__course_type_id=booking.course_type_id,
        )
        .exclude(booking_day__booking_id=booking.pk)
        .order_by("-booking_day__date", "-id")
        .values_list("name", "date_of_birth", "booking_day__date")
    )

    out: dict[tuple, object] = {}
    for name, dob, day_date in rows:
        key = _identity_key(name, dob)
        if key and key in keys and key not in out:
            out[key] = day_date
    return out


def annotate_registers_prior_pass(booking, registers) -> None:
    """Attach prior_pass / prior_pass_date onto each register (or row['obj'])."""
    info = prior_pass_dates_for_booking(booking, registers)
    for item in registers or []:
        reg = item.get("obj") if isinstance(item, dict) else item
        if not reg:
            continue
        key = _identity_key(getattr(reg, "name", None), getattr(reg, "date_of_birth", None))
        prior_date = info.get(key) if key else None
        reg.prior_pass = bool(prior_date)
        reg.prior_pass_date = prior_date
        if isinstance(item, dict):
            item["prior_pass"] = bool(prior_date)
            item["prior_pass_date"] = prior_date

"""Detect delegates with prior pass / fail / DNF history on the same course type."""
from __future__ import annotations

import datetime as dt

from django.db.models import Q
from django.utils import timezone

from ..models import CompetencyAssessment, CourseCompetency, DelegateRegister

DNF_LOOKBACK_DAYS = 365


def _identity_key(name, dob):
    name = (name or "").strip().lower()
    if not name or not dob:
        return None
    return (name, dob)


def _register_day_date(reg):
    return getattr(getattr(reg, "booking_day", None), "date", None) or getattr(reg, "date", None)


def _mandatory_competencies_complete(booking, register) -> bool:
    """True when every active mandatory competency is marked competent/exceeded."""
    if not booking or not booking.course_type_id:
        return False
    mandatory_ids = list(
        CourseCompetency.objects.filter(
            course_type_id=booking.course_type_id,
            is_optional=False,
            is_active=True,
        ).values_list("id", flat=True)
    )
    if not mandatory_ids:
        return False
    achieved = set(
        CompetencyAssessment.objects.filter(
            register=register,
            course_competency_id__in=mandatory_ids,
            level__in=("c", "e"),
        ).values_list("course_competency_id", flat=True)
    )
    return all(cid in achieved for cid in mandatory_ids)


def _counts_as_prior_pass(reg) -> bool:
    """
    True only for a real pass.

    Explicit DNF / Fail are never reinterpreted as a pass, even if some
    competencies were ticked before the course ended.

    Soft fallback: completed booking with blank/pending outcome and all
    mandatory competencies achieved (legacy incomplete outcome data).
    """
    outcome = (getattr(reg, "outcome", None) or "").strip().lower()
    if outcome == "pass":
        return True
    if outcome in ("dnf", "fail"):
        return False

    booking = getattr(getattr(reg, "booking_day", None), "booking", None)
    if not booking or getattr(booking, "status", "") != "completed":
        return False
    return _mandatory_competencies_complete(booking, reg)


def _effective_prior_result(reg) -> str:
    """Return 'pass', 'fail', 'dnf', or '' for a prior register."""
    if _counts_as_prior_pass(reg):
        return "pass"
    outcome = (getattr(reg, "outcome", None) or "").strip().lower()
    if outcome == "fail":
        return "fail"
    if outcome == "dnf":
        return "dnf"
    return ""


def _collect_identity_keys(registers) -> set:
    keys = set()
    for item in registers or []:
        reg = item.get("obj") if isinstance(item, dict) else item
        if not reg:
            continue
        key = _identity_key(getattr(reg, "name", None), getattr(reg, "date_of_birth", None))
        if key:
            keys.add(key)
    return keys


def prior_history_for_booking(booking, registers) -> dict[tuple, dict]:
    """
    Map (name_lower, dob) -> {
      "pass_date": date|None,
      "fail_date": date|None,
      "dnf_date": date|None,
    }

    Only earlier attendances count (never future courses relative to this booking).

    Rules:
    - Prior Pass: any earlier pass on this course type (wins; hides fail/dnf).
    - Previous Fail: earlier fail with no earlier pass after it (no time limit).
    - Previous DNF: earlier DNF within the 12 months before this booking, with no pass since.
    """
    if not booking or not booking.course_type_id:
        return {}

    keys = _collect_identity_keys(registers)
    if not keys:
        return {}

    reference_date = getattr(booking, "course_date", None) or timezone.localdate()
    dnf_cutoff = reference_date - dt.timedelta(days=DNF_LOOKBACK_DAYS)

    q = Q()
    for name, dob in keys:
        q |= Q(name__iexact=name, date_of_birth=dob)

    candidates = (
        DelegateRegister.objects.filter(
            q,
            booking_day__booking__course_type_id=booking.course_type_id,
            booking_day__date__lt=reference_date,
        )
        .exclude(booking_day__booking_id=booking.pk)
        .select_related("booking_day", "booking_day__booking")
        .order_by("-booking_day__date", "-id")
    )

    events_by_key: dict[tuple, list] = {key: [] for key in keys}
    for reg in candidates:
        key = _identity_key(reg.name, reg.date_of_birth)
        if not key or key not in events_by_key:
            continue
        day_date = _register_day_date(reg)
        result = _effective_prior_result(reg)
        if not result or not day_date:
            continue
        # Defence in depth: never treat same-day/future attendances as prior.
        if day_date >= reference_date:
            continue
        events_by_key[key].append((day_date, result))

    out: dict[tuple, dict] = {}
    for key, events in events_by_key.items():
        # events are newest-first, and all are strictly before this booking
        pass_date = next((d for d, r in events if r == "pass"), None)
        if pass_date:
            out[key] = {"pass_date": pass_date, "fail_date": None, "dnf_date": None}
            continue

        fail_date = next((d for d, r in events if r == "fail"), None)
        dnf_date = next(
            (d for d, r in events if r == "dnf" and d >= dnf_cutoff),
            None,
        )
        out[key] = {
            "pass_date": None,
            "fail_date": fail_date,
            "dnf_date": dnf_date,
        }
    return out


def prior_pass_dates_for_booking(booking, registers) -> dict[tuple, object]:
    """Backwards-compatible map of identity -> prior pass date."""
    history = prior_history_for_booking(booking, registers)
    return {
        key: info["pass_date"]
        for key, info in history.items()
        if info.get("pass_date")
    }


def annotate_registers_prior_pass(booking, registers) -> None:
    """Attach prior pass / fail / DNF badge fields onto each register (or row['obj'])."""
    history = prior_history_for_booking(booking, registers)
    for item in registers or []:
        reg = item.get("obj") if isinstance(item, dict) else item
        if not reg:
            continue
        key = _identity_key(getattr(reg, "name", None), getattr(reg, "date_of_birth", None))
        info = history.get(key) if key else None
        pass_date = info.get("pass_date") if info else None
        fail_date = info.get("fail_date") if info else None
        dnf_date = info.get("dnf_date") if info else None

        reg.prior_pass = bool(pass_date)
        reg.prior_pass_date = pass_date
        reg.prior_fail = bool(fail_date)
        reg.prior_fail_date = fail_date
        reg.prior_dnf = bool(dnf_date)
        reg.prior_dnf_date = dnf_date

        if isinstance(item, dict):
            item["prior_pass"] = bool(pass_date)
            item["prior_pass_date"] = pass_date
            item["prior_fail"] = bool(fail_date)
            item["prior_fail_date"] = fail_date
            item["prior_dnf"] = bool(dnf_date)
            item["prior_dnf_date"] = dnf_date

"""
Public delegate certificate portal.

Delegates identify themselves with course date, first name, surname, DOB and
course type. Access to content is gated by Booking.certificates_released.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import CertificatePortalLoginForm
from .models import (
    AssessmentLevel,
    Booking,
    CompetencyAssessment,
    CourseCompetency,
    CourseOutcome,
    DelegateRegister,
    ExamAttempt,
)
from .utils.certificates import build_certificates_pdf_for_booking


SESSION_BOOKING = "cert_portal_booking_id"
SESSION_REGISTER = "cert_portal_register_id"
SESSION_NAME = "cert_portal_name"
SESSION_DOB = "cert_portal_dob"


def _clear_session(request) -> None:
    for key in (SESSION_BOOKING, SESSION_REGISTER, SESSION_NAME, SESSION_DOB):
        request.session.pop(key, None)


def _store_session(request, booking: Booking, register: DelegateRegister) -> None:
    request.session[SESSION_BOOKING] = str(booking.pk)
    request.session[SESSION_REGISTER] = register.pk
    request.session[SESSION_NAME] = (register.name or "").strip()
    dob = register.date_of_birth
    request.session[SESSION_DOB] = dob.isoformat() if dob else ""


def _certificate_expiry_date(booking: Booking) -> date | None:
    base = getattr(booking, "course_date", None)
    if not base:
        return None
    raw = getattr(booking.course_type, "certificate_duration", None) or Decimal("3.0")
    try:
        duration = Decimal(str(raw))
    except Exception:
        duration = Decimal("3.0")
    years = int(duration)
    frac_days = int(((duration - years) * Decimal("365")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    try:
        expiry = base.replace(year=base.year + years)
    except ValueError:
        expiry = base.replace(month=2, day=28, year=base.year + years)
    if frac_days:
        expiry = expiry + timedelta(days=frac_days)
    return expiry


def _format_date_range(booking: Booking) -> str:
    days = list(booking.days.order_by("date").values_list("date", flat=True))
    if not days:
        d = booking.course_date
        return d.strftime("%d %b %Y") if d else "—"
    if len(days) == 1:
        return days[0].strftime("%d %b %Y")
    return f"{days[0].strftime('%d %b %Y')} – {days[-1].strftime('%d %b %Y')}"


_LEVEL_RANK = {
    AssessmentLevel.EXCEEDED: 4,
    AssessmentLevel.COMPETENT: 3,
    AssessmentLevel.NEEDS_IMPROVEMENT: 2,
    AssessmentLevel.NOT_ASSESSED: 1,
}


def _best_outcome(registers) -> str:
    outcomes = {(r.outcome or "").lower() for r in registers}
    if CourseOutcome.PASS in outcomes or "pass" in outcomes:
        return CourseOutcome.PASS
    if CourseOutcome.FAIL in outcomes or "fail" in outcomes:
        return CourseOutcome.FAIL
    if CourseOutcome.DNF in outcomes or "dnf" in outcomes:
        return CourseOutcome.DNF
    return CourseOutcome.PENDING


def _pick_representative_register(registers):
    """Prefer a pass row; otherwise the most recent register."""
    regs = list(registers)
    if not regs:
        return None
    for r in regs:
        if (r.outcome or "").lower() == CourseOutcome.PASS:
            return r
    return sorted(regs, key=lambda r: (r.booking_day.date if r.booking_day_id else date.min, r.pk), reverse=True)[0]


def _topics_for_delegate(booking: Booking, registers) -> list[dict]:
    reg_ids = [r.pk for r in registers]
    required = list(
        CourseCompetency.objects.filter(
            course_type=booking.course_type,
            is_active=True,
            is_optional=False,
        ).order_by("sort_order", "name")
    )
    optional = list(
        booking.optional_modules.filter(is_active=True).order_by("sort_order", "name")
    )
    # de-dupe while preserving order
    seen = set()
    competencies = []
    for c in required + optional:
        if c.pk not in seen:
            seen.add(c.pk)
            competencies.append(c)

    assessments = CompetencyAssessment.objects.filter(
        register_id__in=reg_ids,
        course_competency_id__in=[c.pk for c in competencies],
    )
    best_by_comp: dict[int, str] = {}
    for a in assessments:
        cid = a.course_competency_id
        prev = best_by_comp.get(cid)
        if prev is None or _LEVEL_RANK.get(a.level, 0) > _LEVEL_RANK.get(prev, 0):
            best_by_comp[cid] = a.level

    level_labels = dict(AssessmentLevel.choices)
    rows = []
    for c in competencies:
        level = best_by_comp.get(c.pk, AssessmentLevel.NOT_ASSESSED)
        rows.append({
            "code": c.code,
            "name": c.name,
            "optional": c.is_optional,
            "level": level,
            "level_label": level_labels.get(level, level),
        })
    return rows


def _exam_results_for_delegate(booking: Booking, name: str, dob: date | None) -> list[dict]:
    if not name or not dob:
        return []
    day_dates = list(booking.days.values_list("date", flat=True))
    qs = (
        ExamAttempt.objects.filter(
            exam__course_type=booking.course_type,
            delegate_name__iexact=name,
            date_of_birth=dob,
            finished_at__isnull=False,
        )
        .filter(Q(booking=booking) | Q(booking__isnull=True, exam_date__in=day_dates))
        .select_related("exam")
        .order_by("exam__sequence", "-finished_at", "-pk")
    )
    latest_by_exam: dict[int, ExamAttempt] = {}
    for att in qs:
        if att.exam_id not in latest_by_exam:
            latest_by_exam[att.exam_id] = att

    rows = []
    for att in sorted(latest_by_exam.values(), key=lambda a: a.exam.sequence if a.exam_id else 0):
        total = att.total_questions or 0
        pct = int(round((att.score_correct / total) * 100)) if total else 0
        rows.append({
            "title": att.exam.title or f"Exam {att.exam.sequence}",
            "exam_code": att.exam.exam_code,
            "exam_date": att.exam_date,
            "score_correct": att.score_correct,
            "total_questions": total,
            "percent": pct,
            "passed": att.passed,
        })
    return rows


def _resolve_session(request):
    booking_id = request.session.get(SESSION_BOOKING)
    register_id = request.session.get(SESSION_REGISTER)
    if not booking_id or not register_id:
        return None, None, []
    try:
        booking = (
            Booking.objects.select_related(
                "course_type", "instructor", "business", "training_location"
            )
            .prefetch_related("days", "optional_modules")
            .get(pk=booking_id)
        )
    except Booking.DoesNotExist:
        _clear_session(request)
        return None, None, []

    name = (request.session.get(SESSION_NAME) or "").strip()
    dob_raw = request.session.get(SESSION_DOB) or ""
    try:
        dob = date.fromisoformat(dob_raw) if dob_raw else None
    except ValueError:
        dob = None

    registers = list(
        DelegateRegister.objects.filter(booking_day__booking=booking)
        .filter(name__iexact=name)
        .filter(date_of_birth=dob)
        .select_related("booking_day")
        .order_by("booking_day__date", "id")
    )
    if not registers:
        # Fall back to the stored register id (name may have been corrected)
        try:
            reg = DelegateRegister.objects.select_related("booking_day").get(
                pk=register_id, booking_day__booking=booking
            )
        except DelegateRegister.DoesNotExist:
            _clear_session(request)
            return None, None, []
        registers = list(
            DelegateRegister.objects.filter(
                booking_day__booking=booking,
                name__iexact=reg.name,
                date_of_birth=reg.date_of_birth,
            ).select_related("booking_day")
        )
        if not registers:
            registers = [reg]

    representative = _pick_representative_register(registers)
    return booking, representative, registers


def _match_registers(course_type, course_date, full_name, dob):
    return list(
        DelegateRegister.objects.filter(
            booking_day__booking__course_type=course_type,
            booking_day__date=course_date,
            date_of_birth=dob,
            name__iexact=full_name,
        )
        .select_related(
            "booking_day__booking__course_type",
            "booking_day__booking__instructor",
            "booking_day__booking__business",
        )
        .order_by("id")
    )


@require_http_methods(["GET", "POST"])
def certificate_portal_login(request):
    if request.method == "GET" and request.session.get(SESSION_BOOKING):
        booking, reg, _ = _resolve_session(request)
        if booking and reg:
            if booking.certificates_released:
                return redirect("certificate_portal_home")
            return redirect("certificate_portal_awaiting")

    form = CertificatePortalLoginForm(request.POST or None)
    error = None

    if request.method == "POST" and form.is_valid():
        full_name = form.cleaned_full_name()
        course_date = form.cleaned_data["course_date"]
        dob = form.cleaned_data["date_of_birth"]
        course_type = form.cleaned_data["course_type"]

        matches = _match_registers(course_type, course_date, full_name, dob)
        if not matches:
            error = (
                "We could not find a matching course record. "
                "Please check your details and try again."
            )
        else:
            booking_ids = {m.booking_day.booking_id for m in matches}
            if len(booking_ids) > 1:
                error = (
                    "More than one matching course was found for those details. "
                    "Please contact your training provider for help."
                )
            else:
                booking = matches[0].booking_day.booking
                # All registers for this person on the booking (any day)
                all_regs = list(
                    DelegateRegister.objects.filter(
                        booking_day__booking=booking,
                        name__iexact=full_name,
                        date_of_birth=dob,
                    ).select_related("booking_day")
                )
                representative = _pick_representative_register(all_regs) or matches[0]
                _store_session(request, booking, representative)
                if booking.certificates_released:
                    return redirect("certificate_portal_home")
                return redirect("certificate_portal_awaiting")

    return render(request, "public/certificate_portal_login.html", {
        "form": form,
        "error": error,
    })


@require_http_methods(["GET"])
def certificate_portal_awaiting(request):
    booking, reg, _ = _resolve_session(request)
    if not booking or not reg:
        return redirect("certificate_portal_login")
    if booking.certificates_released:
        return redirect("certificate_portal_home")
    return render(request, "public/certificate_portal_awaiting.html", {
        "booking": booking,
        "register": reg,
        "dates_display": _format_date_range(booking),
    })


@require_http_methods(["GET"])
def certificate_portal_home(request):
    booking, reg, registers = _resolve_session(request)
    if not booking or not reg:
        return redirect("certificate_portal_login")
    if not booking.certificates_released:
        return redirect("certificate_portal_awaiting")

    outcome = _best_outcome(registers)
    passed = outcome == CourseOutcome.PASS
    expiry = _certificate_expiry_date(booking) if passed else None

    return render(request, "public/certificate_portal.html", {
        "booking": booking,
        "register": reg,
        "registers": registers,
        "dates_display": _format_date_range(booking),
        "outcome": outcome,
        "outcome_label": dict(CourseOutcome.choices).get(outcome, outcome),
        "passed": passed,
        "expiry_date": expiry,
        "certificate_name": reg.certificate_display_name() if passed else "",
        "topics": _topics_for_delegate(booking, registers),
        "exam_results": _exam_results_for_delegate(
            booking, reg.name, reg.date_of_birth
        ),
    })


@require_http_methods(["GET"])
def certificate_portal_pdf(request):
    booking, reg, registers = _resolve_session(request)
    if not booking or not reg:
        return redirect("certificate_portal_login")
    if not booking.certificates_released:
        return redirect("certificate_portal_awaiting")
    if _best_outcome(registers) != CourseOutcome.PASS:
        return redirect("certificate_portal_home")

    # Prefer the pass register for PDF name overlay
    pass_reg = _pick_representative_register(
        [r for r in registers if (r.outcome or "").lower() == CourseOutcome.PASS]
    ) or reg

    result = build_certificates_pdf_for_booking(booking, registers=[pass_reg])
    if not result:
        return redirect("certificate_portal_home")

    filename, pdf_bytes = result
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp


@require_http_methods(["GET", "POST"])
def certificate_portal_logout(request):
    _clear_session(request)
    return redirect("certificate_portal_login")

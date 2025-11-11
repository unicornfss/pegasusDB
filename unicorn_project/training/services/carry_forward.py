# unicorn_project/training/services/carry_forward.py
from datetime import timedelta
from django.utils import timezone

CF_NOTE_LINE = "[CF-DNF] Match found with a previous registration; prior achieved competencies have been carried over."

def _append_cf_note(reg):
    # assumes model field is "notes" (string/TextField). Adjust if your field name differs.
    notes = (getattr(reg, "notes", "") or "").strip()
    if CF_NOTE_LINE not in notes.splitlines():
        new_notes = (notes + ("\n" if notes else "") + CF_NOTE_LINE)
        setattr(reg, "notes", new_notes)
        reg.save(update_fields=["notes"])

def _remove_cf_note(reg):
    notes = (getattr(reg, "notes", "") or "")
    lines = [ln for ln in notes.splitlines() if ln.strip() != CF_NOTE_LINE]
    new_notes = "\n".join(lines).strip()
    if new_notes != notes.strip():
        setattr(reg, "notes", new_notes)
        reg.save(update_fields=["notes"])

def carry_forward_competencies(new_reg):
    """
    If the same delegate (name + dob) had a DNF for the same course type
    in the last 2 years, copy any competencies already achieved as locked ticks.
    Also manages a tagged note on the register.
    Returns number of competencies carried forward.
    """
    from ..models import DelegateRegister, CompetencyAssessment  # local to avoid cycles

    if not (new_reg and new_reg.booking_day_id):
        _remove_cf_note(new_reg)
        return 0

    bd = new_reg.booking_day
    course_type = getattr(bd.booking, "course_type", None)
    dob = getattr(new_reg, "date_of_birth", None)
    name = (getattr(new_reg, "name", "") or "").strip()

    if not (name and dob and course_type):
        _remove_cf_note(new_reg)
        return 0

    # If we already have any locked carried items, skip (idempotent)
    # (Note: when identity changes we delete them before calling this.)
    if CompetencyAssessment.objects.filter(register=new_reg, is_locked=True).exists():
        # Ensure note is present if there ARE locked items
        _append_cf_note(new_reg)
        return CompetencyAssessment.objects.filter(register=new_reg, is_locked=True).count()

    two_years_ago = timezone.localdate() - timedelta(days=730)

    prior = (DelegateRegister.objects
             .filter(
                 name__iexact=name,
                 date_of_birth=dob,
                 outcome='dnf',
                 booking_day__booking__course_type=course_type,
                 booking_day__date__gte=two_years_ago,
                 booking_day__date__lt=bd.date,
             )
             .order_by('-booking_day__date', '-id')
             .first())

    if not prior:
        _remove_cf_note(new_reg)
        return 0

    prev_assessments = (CompetencyAssessment.objects
                        .filter(register=prior, level__in=['c', 'e'])
                        .select_related('course_competency'))

    created_count = 0
    for pa in prev_assessments:
        ca, created = CompetencyAssessment.objects.get_or_create(
            register=new_reg,
            course_competency=pa.course_competency,
            defaults={
                "level": pa.level,
                "assessed_by": getattr(new_reg, "instructor", None),
                "is_locked": True,
                "source_note": f"carried from DNF on {prior.booking_day.date:%Y-%m-%d}",
            },
        )
        if not created:
            if ca.level in ('na', 'p'):
                ca.level = pa.level
            ca.is_locked = True
            ca.source_note = f"carried from DNF on {prior.booking_day.date:%Y-%m-%d}"
            ca.save(update_fields=['level', 'is_locked', 'source_note'])
        created_count += 1

    # manage the tagged note
    if created_count > 0:
        _append_cf_note(new_reg)
    else:
        _remove_cf_note(new_reg)

    return created_count

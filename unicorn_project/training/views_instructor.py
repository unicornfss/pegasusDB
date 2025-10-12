import io
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Max
from django.forms import modelformset_factory
from django.http import JsonResponse, HttpResponseForbidden, FileResponse, HttpResponseNotAllowed
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from .models import Instructor, Booking, BookingDay, DelegateRegister, CourseCompetency
from .forms import DelegateRegisterInstructorForm, BookingNotesForm 

buffer = io.BytesIO()
c = canvas.Canvas(buffer, pagesize=landscape(A4))
W, H = landscape(A4)   # use these for your coordinates

HEALTH_BADGE = {
    "fit":            ("✔", "bg-success", "Fit to take part"),
    "agreed_adjust":  ("■", "bg-warning text-dark", "Impairment – agreed adjustments"),
    "will_discuss":   ("▲", "bg-orange text-dark" if False else "bg-warning", "Impairment – will discuss"),
    "not_fit":        ("✖", "bg-danger", "Not fit to take part"),
}
# Note: Bootstrap has no orange by default; we re-use warning (yellow).

def _health_badge_tuple(code: str):
    return HEALTH_BADGE.get(code or "", ("–", "bg-secondary", "Not provided"))

@login_required
def instructor_dashboard(request):
    # Just forward to the main list
    return redirect("instructor_bookings")

def _get_instructor(user):
    """Return the Instructor linked to this user (or None)."""
    if not user.is_authenticated:
        return None
    return Instructor.objects.filter(user=user).first()

@login_required
def post_login(request):
    """
    Smart landing after login:
    - If user is linked to an Instructor -> go to their upcoming bookings
    - If user is staff -> go to admin dashboard
    - Else -> fall back to instructor bookings (safe)
    """
    inst = _get_instructor(request.user)
    if inst:
        return redirect("instructor_bookings")
    if request.user.is_staff:
        return redirect("app_admin_dashboard")
    return redirect("instructor_bookings")


@login_required
def instructor_bookings(request):
    """
    Instructor’s upcoming bookings:
    Order & limit:
      1) in_progress (all)
      2) awaiting_closure (all)
      3) scheduled (up to 10, from today onwards)
    Cancelled are excluded.
    """
    inst = _get_instructor(request.user)
    if not inst:
        messages.error(request, "Your user account isn’t linked to an instructor record.")
        # Send non-instructors somewhere sensible (admin if staff, else home)
        return redirect("app_admin_dashboard" if request.user.is_staff else "home")

    today = timezone.localdate()

    base_qs = (
        Booking.objects
        .select_related("course_type", "business", "training_location")
        .filter(instructor=inst)
        .exclude(status="cancelled")
    )

    in_progress = (
        base_qs.filter(status="in_progress")
        .order_by("course_date", "start_time")
    )
    awaiting = (
        base_qs.filter(status="awaiting_closure")
        .order_by("course_date", "start_time")
    )
    scheduled = (
        base_qs.filter(status="scheduled", course_date__gte=today)
        .order_by("course_date", "start_time")[:10]
    )

    return render(request, "instructor/bookings.html", {
        "title": "My bookings",
        "instructor": inst,
        "in_progress": in_progress,
        "awaiting": awaiting,
        "scheduled": scheduled,
    })

@login_required
def whoami(request):
    user = request.user
    is_instructor = False
    try:
        # If user ↔ Instructor is OneToOne with related_name='instructor'
        is_instructor = hasattr(user, "instructor") and user.instructor is not None
    except Instructor.DoesNotExist:
        is_instructor = False

    return JsonResponse({
        "username": user.username,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "has_instructor_link": is_instructor,
        "session_role": request.session.get("role"),
    })

def _get_user_instructor(user):
    """Return Instructor linked to this user (or None)."""
    if not user.is_authenticated:
        return None
    return Instructor.objects.filter(user=user).first()

def _assessment_context(booking, user):
    # permissions: staff or assigned instructor
    if not (user.is_staff or (booking.instructor and getattr(booking.instructor, "user_id", None) == user.id)):
        raise PermissionError("Not your booking.")

    # --- Delegates: ALL days for this booking (no final-day restriction) ---
    delegates = list(
        DelegateRegister.objects
        .filter(booking_day__booking=booking)
        .order_by("name", "id")
    )

    # --- Competencies: all for this course type (no is_active filter) ---
    competencies = list(
        CourseCompetency.objects
        .filter(course_type=booking.course_type)
        .order_by("sort_order", "name", "id")
    )

    # --- Existing assessments: (register_id, competency_id) -> object ---
    existing = {}
    if delegates and competencies:
        try:
            from .models import CompetencyAssessment  # lazy import
            qs = (
                CompetencyAssessment.objects
                .filter(register__in=delegates, course_competency__in=competencies)
                .select_related("register", "course_competency")
            )
            for a in qs:
                existing[(a.register_id, a.course_competency_id)] = a
        except Exception:
            existing = {}

    # Levels (fallback if enum not present)
    try:
        from .models import AssessmentLevel
        levels = AssessmentLevel.choices
    except Exception:
        levels = (("na", "Not assessed"), ("c", "Competent"))

    return {
        "delegates": delegates,
        "competencies": competencies,
        "existing": existing,
        "levels": levels,
    }

@login_required
def instructor_booking_detail(request, pk):
    """Instructor course detail with per-day delegate counts and an edit link."""
    instr = getattr(request.user, "instructor", None)
    booking = get_object_or_404(
        Booking.objects.select_related("course_type", "business", "instructor", "training_location"),
        pk=pk
    )

    # only its instructor can see
    if not instr or booking.instructor_id != instr.id:
        messages.error(request, "You do not have access to this booking.")
        return redirect("instructor_bookings")

    # --- NEW: handle booking_notes form on this page ---
    if request.method == "POST":
        notes_form = BookingNotesForm(request.POST, instance=booking)
        if notes_form.is_valid():
            notes_form.save()
            messages.success(request, "Course notes saved.")
            return redirect("instructor_booking_detail", pk=booking.pk)
    else:
        notes_form = BookingNotesForm(instance=booking)

    # days list with counts
    days = (
        BookingDay.objects
        .filter(booking=booking)
        .order_by("date")
        .annotate(n=Count("delegateregister"))
    )

    day_rows = []
    for d in days:
        day_rows.append({
            "id": d.id,
            "date": date_format(d.date, "j M Y"),  # 21 Oct 2025
            "start_time": d.start_time,
            "n": d.n or 0,
            "edit_url": redirect("instructor_day_registers", pk=d.id).url,
        })

    ctx = {
        "title": booking.course_type.name,
        "booking": booking,
        "day_rows": day_rows,
        "back_url": redirect("instructor_bookings").url,
        "notes_form": notes_form,
        "has_exam": getattr(booking.course_type, "has_exam", False),
    }

    # Add assessment matrix data for the tab
    try:
        ctx.update(_assessment_context(booking, request.user))
    except PermissionError:
        ctx.update({"delegates": [], "competencies": [], "existing": {}, "levels": []})

    return render(request, "instructor/booking_detail.html", ctx)





@login_required
def instructor_day_registers(request, pk: int):
    """
    Read-only list of delegates for a day, with coloured health indicator and Edit/Delete buttons.
    """
    instr = getattr(request.user, "instructor", None)
    day = get_object_or_404(
        BookingDay.objects.select_related(
            "booking__course_type", "booking__business", "booking__instructor"
        ),
        pk=pk,
    )
    if not instr or day.booking.instructor_id != instr.id:
        messages.error(request, "You do not have access to this register.")
        return redirect("instructor_bookings")

    # Pull only what we need, sorted alphabetically by name
    qs = (
        DelegateRegister.objects.filter(booking_day=day)
        .order_by("name")  # alphabetical
        .only("name", "date_of_birth", "job_title", "employee_id", "health_status", "notes")
    )

    rows = []
    for r in qs:
        symbol, cls, title = _health_badge_tuple(r.health_status)
        rows.append({
            "obj": r,
            "health_symbol": symbol,
            "health_class": cls,
            "health_title": title,
        })

    return render(request, "instructor/day_registers.html", {
        "title": f"Registers — {day.booking.course_type.name} — {date_format(day.date, 'j M Y')}",
        "day": day,
        "rows": rows,
        "back_url": redirect("instructor_booking_detail", pk=day.booking_id).url,
        "legend": [
            ("✔", "bg-success", "Fit to take part"),
            ("■", "bg-warning text-dark", "Impairment – agreed adjustments"),
            ("▲", "bg-warning", "Impairment – will discuss with instructor"),
            ("✖", "bg-danger", "Not fit to take part today"),
        ],
    })


@login_required
@transaction.atomic
def instructor_delegate_edit(request, pk: int):
    """
    Edit a single delegate row (instructor locked to the logged-in instructor).
    """
    instr = getattr(request.user, "instructor", None)
    reg = get_object_or_404(
        DelegateRegister.objects.select_related("booking_day__booking__instructor"),
        pk=pk
    )
    if not instr or reg.booking_day.booking.instructor_id != instr.id:
        messages.error(request, "You do not have access to edit this delegate.")
        return redirect("instructor_bookings")

    if request.method == "POST" and "delete" in request.POST:
        reg.delete()
        messages.success(request, "Delegate removed.")
        return redirect("instructor_day_registers", pk=reg.booking_day_id)

    if request.method == "POST":
        form = DelegateRegisterInstructorForm(
            request.POST, instance=reg, current_instructor=instr
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Delegate updated.")
            return redirect("instructor_day_registers", pk=reg.booking_day_id)
    else:
        form = DelegateRegisterInstructorForm(
            instance=reg, current_instructor=instr
        )

    return render(request, "instructor/delegate_form.html", {
        "title": f"Edit delegate — {reg.name}",
        "form": form,
        "reg": reg,
        "day": reg.booking_day,
        "back_url": redirect("instructor_day_registers", pk=reg.booking_day_id).url,
    })


@login_required
@transaction.atomic
def instructor_delegate_new(request, day_pk: int):
    """
    Create a new delegate row for a day.
    """
    instr = getattr(request.user, "instructor", None)
    day = get_object_or_404(
        BookingDay.objects.select_related("booking__instructor", "booking__course_type"),
        pk=day_pk
    )
    if not instr or day.booking.instructor_id != instr.id:
        messages.error(request, "You do not have access to this register.")
        return redirect("instructor_bookings")

    if request.method == "POST":
        form = DelegateRegisterInstructorForm(request.POST, current_instructor=instr)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.booking_day = day
            if not obj.date:
                obj.date = timezone.localdate()
            obj.save()
            messages.success(request, "Delegate added.")
            return redirect("instructor_day_registers", pk=day.pk)
    else:
        form = DelegateRegisterInstructorForm(current_instructor=instr)

    return render(request, "instructor/delegate_form.html", {
        "title": "Add delegate",
        "form": form,
        "day": day,
        "back_url": redirect("instructor_day_registers", pk=day.pk).url,
    })

@login_required
def instructor_register_edit(request, pk: int):
    instr = getattr(request.user, "instructor", None)
    reg = get_object_or_404(
        DelegateRegister.objects.select_related("booking_day__booking__course_type"),
        pk=pk
    )
    if not instr or reg.instructor_id != instr.id:
        messages.error(request, "You do not have access to edit this delegate.")
        return redirect("instructor_bookings")

    if request.method == "POST":
        form = DelegateRegisterInstructorForm(
            request.POST,
            instance=reg,
            current_instructor=instr,
        )
        if form.is_valid():
            obj = form.save(commit=False)
            obj.instructor = instr   # harden
            obj.save()
            messages.success(request, "Delegate updated.")
            return redirect("instructor_day_registers", pk=reg.booking_day_id)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = DelegateRegisterInstructorForm(
            instance=reg,
            current_instructor=instr,
        )

    day = reg.booking_day
    return render(
        request,
        "instructor/register_edit.html",
        {
            "title": f"Edit delegate — {reg.name}",
            "form": form,
            "reg": reg,
            "day": day,
            "back_url": redirect("instructor_day_registers", pk=day.pk).url,
        },
    )

@login_required
def instructor_delegate_delete(request, pk: int):
    """Delete a single DelegateRegister row (POST only, with confirm)."""
    instr = getattr(request.user, "instructor", None)
    reg = get_object_or_404(
        DelegateRegister.objects.select_related("booking_day__booking"),
        pk=pk
    )
    if not instr or reg.booking_day.booking.instructor_id != instr.id:
        messages.error(request, "You do not have permission to delete this delegate.")
        return redirect("instructor_bookings")

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    day_pk = reg.booking_day_id
    reg.delete()
    messages.success(request, "Delegate deleted.")
    return redirect("instructor_day_registers", pk=day_pk)


@login_required
def instructor_day_registers_pdf(request, pk: int):
    """
    Register PDF for a single day, in LANDSCAPE, with:
    - Header: Business, Course reference, Instructor, This day’s date
    - Footer on every page with Unicorn contact details
    - Health declaration column (full text per row)
    """
    instr = getattr(request.user, "instructor", None)
    day = get_object_or_404(
        BookingDay.objects.select_related(
            "booking__course_type", "booking__business", "booking__instructor"
        ),
        pk=pk
    )
    if not instr or day.booking.instructor_id != instr.id:
        messages.error(request, "You do not have access to this register.")
        return redirect("instructor_bookings")

    regs = list(
        DelegateRegister.objects.filter(booking_day=day)
        .order_by("name")
        .only("name", "date_of_birth", "job_title", "employee_id", "health_status", "notes")
    )

    # --- PDF setup ---
    import io, textwrap
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm

    buf = io.BytesIO()
    pagesize = landscape(A4)
    c = canvas.Canvas(buf, pagesize=pagesize)
    W, H = pagesize

    left   = 15*mm
    right  = W - 15*mm
    top    = H - 15*mm
    bottom = 15*mm

    # Footer (each page)
    FOOTER_TEXT = "Unicorn Fire & Safety Solutions, Unicorn House, 6 Salendine, Shrewsbury, SY1 3XJ: info@unicornsafety.co.uk: 01743 360211"
    def draw_footer():
        c.saveState()
        try:
            c.setFont("Helvetica", 8)
            c.setFillGray(0.35)
            c.drawString(left, bottom - 6*mm, FOOTER_TEXT)
            c.setFillGray(0)
        finally:
            c.restoreState()

    # Helpers
    def fmt_date(d):
        # Windows-safe date like '21 Oct 2025'
        return f"{d.day} {d.strftime('%b %Y')}"

    # Column layout (mm -> points via units)
    # Name | DOB | Job title | Emp ID | Health declaration
    col_name   = 62*mm
    col_dob    = 24*mm
    col_job    = 46*mm
    col_emp    = 22*mm
    col_health = (right - left) - (col_name + col_dob + col_job + col_emp)

    row_min_h   = 12*mm          # minimum row height
    line_gap    = 4              # points between wrapped lines
    body_fs     = 9
    small_fs    = 8

    def wrap_to_width(text, font="Helvetica", size=9, max_width=col_health-4*mm):
        if not text:
            return [""]
        # quick word-wrap using textwrap; then ensure width via a second pass
        c.setFont(font, size)
        # rough char estimate to seed wrap width
        approx_chars = max(12, int(max_width / (size * 0.5)))
        lines = []
        for para in str(text).splitlines():
            for chunk in textwrap.wrap(para, width=approx_chars):
                # final hard trim if still too wide
                while c.stringWidth(chunk, font, size) > max_width and len(chunk) > 1:
                    chunk = chunk[:-1]
                lines.append(chunk)
        return lines or [""]

    # Header block
    y = top
    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, f"{day.booking.course_type.name} — Daily Register")
    y -= 6*mm
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Business: {day.booking.business.name}")
    y -= 5*mm
    c.drawString(left, y, f"Course reference: {day.booking.course_reference or '—'}")
    y -= 5*mm
    c.drawString(left, y, f"Instructor: {day.booking.instructor.name if day.booking.instructor else '—'}")
    y -= 5*mm
    c.drawString(left, y, f"Date: {fmt_date(day.date)}")
    y -= 8*mm

    def draw_header_row():
        nonlocal y
        # Header band
        c.setFillGray(0.95)
        c.rect(left, y-10*mm, (right-left), 10*mm, stroke=0, fill=1)
        c.setFillGray(0)
        c.setFont("Helvetica-Bold", 9)
        x = left
        def cell(w, label):
            c.rect(x, y-10*mm, w, 10*mm, stroke=1, fill=0)
            c.drawCentredString(x + w/2, y-10*mm + 3.5*mm, label)
        cell(col_name,   "Name")
        x += col_name
        cell(col_dob,    "DOB")
        x += col_dob
        cell(col_job,    "Job title")
        x += col_job
        cell(col_emp,    "Emp. ID")
        x += col_emp
        cell(col_health, "Health declaration")
        y -= 10*mm
        c.setFont("Helvetica", body_fs)

    def new_page(continued=False):
        nonlocal y
        # footer + new page
        draw_footer()
        c.showPage()
        y = H - 15*mm
        # repeat header block
        c.setFont("Helvetica-Bold", 14)
        title = f"{day.booking.course_type.name} — Daily Register"
        if continued:
            title += " (cont.)"
        c.drawString(left, y, title)
        y -= 6*mm
        c.setFont("Helvetica", 10)
        c.drawString(left, y, f"Business: {day.booking.business.name}")
        y -= 5*mm
        c.drawString(left, y, f"Course reference: {day.booking.course_reference or '—'}")
        y -= 5*mm
        c.drawString(left, y, f"Instructor: {day.booking.instructor.name if day.booking.instructor else '—'}")
        y -= 5*mm
        c.drawString(left, y, f"Date: {fmt_date(day.date)}")
        y -= 8*mm
        draw_header_row()

    # first header row
    draw_header_row()

    # Rows
    for idx, r in enumerate(regs, start=1):
        # compute wrapped lines for health declaration
        health_text = r.get_health_status_display() if hasattr(r, "get_health_status_display") else ""
        health_lines = wrap_to_width(health_text, size=body_fs, max_width=col_health - 4*mm)
        # job title might need a tiny wrap too
        job_lines = wrap_to_width(r.job_title or "", size=body_fs, max_width=col_job - 4*mm)
        line_height = body_fs + line_gap
        needed_h = max(row_min_h, (max(len(health_lines), len(job_lines)) * line_height) + 6)  # + padding

        # page break guard
        if y - needed_h < bottom + 18*mm:
            new_page(continued=True)

        # zebra band
        if idx % 2 == 0:
            c.setFillGray(0.90)
            c.rect(left, y-needed_h, (right-left), needed_h, stroke=0, fill=1)
            c.setFillGray(0)

        # draw cells & content
        x = left
        # Name
        c.rect(x, y-needed_h, col_name, needed_h, stroke=1, fill=0)
        c.setFont("Helvetica", body_fs)
        c.drawString(x + 2*mm, y - needed_h + 3 + line_height*(len(job_lines) > 1 and 0 or 0), r.name or "—")
        x += col_name

        # DOB
        c.rect(x, y-needed_h, col_dob, needed_h, stroke=1, fill=0)
        c.drawString(x + 2*mm, y - needed_h + 3, r.date_of_birth.strftime("%d/%m/%Y") if r.date_of_birth else "—")
        x += col_dob

        # Job title (wrapped)
        c.rect(x, y-needed_h, col_job, needed_h, stroke=1, fill=0)
        yy = y - 4 - body_fs
        for line in job_lines[:4]:
            c.drawString(x + 2*mm, yy, line)
            yy -= line_height
        x += col_job

        # Employee ID
        c.rect(x, y-needed_h, col_emp, needed_h, stroke=1, fill=0)
        c.drawString(x + 2*mm, y - needed_h + 3, r.employee_id or "—")
        x += col_emp

        # Health declaration (wrapped)
        c.rect(x, y-needed_h, col_health, needed_h, stroke=1, fill=0)
        yy = y - 4 - body_fs
        for line in health_lines[:6]:
            c.drawString(x + 2*mm, yy, line)
            yy -= line_height

        y -= needed_h

    # Legend (optional – keep concise)
    y -= 6*mm
    c.setFont("Helvetica", small_fs)
    c.drawString(left, y, "Health declaration text shown as recorded by the delegate on the day.")

    # last-page footer and save
    draw_footer()
    c.save()
    buf.seek(0)
    filename = f"register_{day.date.strftime('%Y%m%d')}.pdf"
    return FileResponse(buf, as_attachment=True, filename=filename)


@login_required
def instructor_assessment_matrix(request, pk):
    """
    Placeholder view for the assessment matrix.
    Loads the booking and renders the matrix template with empty data.
    We'll wire delegates/competencies next.
    """
    booking = get_object_or_404(Booking, pk=pk)

    # Only assigned instructor or staff can view
    if not (request.user.is_staff or (booking.instructor and getattr(booking.instructor, "user_id", None) == request.user.id)):
        return HttpResponseForbidden("You are not assigned to this booking.")

    context = {
        "booking": booking,
        "delegates": [],        # TODO: populate from your DelegateRegister(s)
        "competencies": [],     # TODO: populate from CourseCompetency for booking.course_type
        "existing": {},         # TODO: map of (register_id, competency_id) -> assessment obj
    }
    return render(request, "instructor/assessment_matrix.html", context)

@login_required
@transaction.atomic
def instructor_assessment_save(request, pk):
    booking = get_object_or_404(Booking, pk=pk)
    instr = getattr(request.user, "instructor", None)
    if not (request.user.is_staff or (instr and booking.instructor_id == instr.id)):
        return HttpResponseForbidden("You are not assigned to this booking.")

    if request.method != "POST":
        return redirect(f"{reverse('instructor_booking_detail', kwargs={'pk': booking.id})}#assessments-tab")

    # guard: only registers for this booking; only competencies for this course type
    delegates = list(DelegateRegister.objects.filter(booking_day__booking=booking).only("id", "outcome"))
    comps = list(CourseCompetency.objects.filter(course_type=booking.course_type).only("id"))
    reg_map = {str(r.id): r for r in delegates}
    comp_ids = [str(c.id) for c in comps]

    # models
    from .models import CompetencyAssessment, AssessmentLevel, CourseOutcome
    valid_levels = {c[0] for c in AssessmentLevel.choices}
    valid_outcomes = {c[0] for c in CourseOutcome.choices}

    created = updated = 0

    # --- Save per-cell levels ---
    for key, val in request.POST.items():
        if not key.startswith("level_"):
            continue
        try:
            _, rid, cid = key.split("_", 2)
        except ValueError:
            continue
        if rid not in reg_map or cid not in comp_ids:
            continue

        level = val if val in valid_levels else "na"
        obj, was_created = CompetencyAssessment.objects.get_or_create(
            register_id=reg_map[rid].id,
            course_competency_id=cid,
            defaults={"level": level, "assessed_by_id": booking.instructor_id},
        )
        if was_created:
            created += 1
        else:
            if obj.level != level or obj.assessed_by_id != booking.instructor_id:
                obj.level = level
                obj.assessed_by_id = booking.instructor_id
                obj.save(update_fields=["level", "assessed_by", "assessed_at"])
                updated += 1

    # --- Save per-delegate outcome, enforcing PASS if all comps competent ---
    for rid, reg in reg_map.items():
        posted_outcome = request.POST.get(f"outcome_{rid}", "pending")
        if posted_outcome not in valid_outcomes:
            posted_outcome = "pending"

        all_competent = True
        for cid in comp_ids:
            if request.POST.get(f"level_{rid}_{cid}", "na") not in {"c", "e"}:
                all_competent = False
                break
        final_outcome = "pass" if all_competent else posted_outcome

        if getattr(reg, "outcome", None) != final_outcome:
            reg.outcome = final_outcome
            reg.save(update_fields=["outcome"])

    messages.success(request, f"Saved {created} new and {updated} updated assessment entr{'y' if (created+updated)==1 else 'ies'}.")
    return redirect(f"{reverse('instructor_booking_detail', kwargs={'pk': booking.id})}#assessments-tab")

@login_required
def instructor_assessment_pdf(request, pk):
    """
    Export the assessment matrix (landscape PDF) with:
    - Business name, course reference, instructor, full set of course dates
    - Dynamic header height / font size so rotated names are readable
    - Darker zebra striping for rows
    - Footer on every page with Unicorn contact details
    Blocks export if any delegate outcome is 'pending'.
    """
    instr = getattr(request.user, "instructor", None)
    booking = get_object_or_404(
        Booking.objects.select_related("course_type", "business", "instructor", "training_location"),
        pk=pk
    )
    if not instr or booking.instructor_id != instr.id:
        messages.error(request, "You do not have access to this booking.")
        return redirect("instructor_bookings")

    # Delegates & competencies
    delegates = list(
        DelegateRegister.objects
        .filter(booking_day__booking=booking)
        .order_by("name", "id")
        .only("id", "name", "outcome")
    )
    competencies = list(
        CourseCompetency.objects
        .filter(course_type=booking.course_type, is_active=True)
        .order_by("sort_order", "name", "id")
        .only("id", "name", "code", "sort_order")
    )

    # Guard: no export if any Pending
    any_pending = any((d.outcome or "pending") == "pending" for d in delegates)
    if any_pending:
        messages.error(request, "Cannot export PDF while any delegate is Pending. Please set each delegate to Pass, Fail, or DNF first.")
        return redirect(f"{reverse('instructor_booking_detail', kwargs={'pk': booking.id})}#assessments-tab")

    # Assessment map
    from .models import CompetencyAssessment, BookingDay
    assess_map = {}
    if delegates and competencies:
        for rid, cid, lvl in (
            CompetencyAssessment.objects
            .filter(register__in=delegates, course_competency__in=competencies)
            .values_list("register_id", "course_competency_id", "level")
        ):
            assess_map[(rid, cid)] = lvl

    # Course dates (all days)
    day_dates = list(
        BookingDay.objects.filter(booking=booking).order_by("date").values_list("date", flat=True)
    )

    # Windows-safe date formatting
    def format_course_dates(dates):
        if not dates:
            return "—"
        ds = list(dates)
        def d_full(d): return f"{d.day} {d.strftime('%b %Y')}"
        def d_mon(d):  return f"{d.day} {d.strftime('%b')}"
        def d_day(d):  return f"{d.day}"
        consecutive = len(ds) <= 1 or all((ds[i+1] - ds[i]).days in (0, 1) for i in range(len(ds)-1))
        if len(ds) >= 2 and consecutive:
            first, last = ds[0], ds[-1]
            if first.year == last.year:
                if first.month == last.month:
                    return f"{d_day(first)}–{d_full(last)}"
                return f"{d_mon(first)}–{d_full(last)}"
            return f"{d_full(first)}–{d_full(last)}"
        parts = [d_full(d) for d in ds[:6]]
        if len(ds) > 6:
            parts.append("…")
        return ", ".join(parts)

    # --- PDF ---
    import io
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm

    buf = io.BytesIO()
    pagesize = landscape(A4)
    c = canvas.Canvas(buf, pagesize=pagesize)
    W, H = pagesize

    left   = 15*mm
    right  = W - 15*mm
    top    = H - 15*mm
    bottom = 15*mm

    # Footer helper (draw on the current page)
    FOOTER_TEXT = "Unicorn Fire & Safety Solutions, Unicorn House, 6 Salendine, Shrewsbury, SY1 3XJ: info@unicornsafety.co.uk: 01743 360211"
    def draw_footer():
        c.saveState()
        try:
            c.setFont("Helvetica", 8)
            c.setFillGray(0.35)
            c.drawString(left, bottom - 6*mm, FOOTER_TEXT)
            c.setFillGray(0)
        finally:
            c.restoreState()

    # Base sizing
    comp_w = 85*mm
    ncols  = max(1, len(delegates))

    # Dynamic header height + font for readability
    if ncols <= 8:
        header_h = 20*mm
        name_fs  = 8
        del_w_min, del_w_max = 18*mm, 28*mm
    elif ncols <= 12:
        header_h = 18*mm
        name_fs  = 7
        del_w_min, del_w_max = 16*mm, 26*mm
    else:
        header_h = 16*mm
        name_fs  = 6
        del_w_min, del_w_max = 14*mm, 24*mm

    del_w   = max(del_w_min, (right - left - comp_w) / ncols)
    del_w   = min(del_w, del_w_max)
    table_w = comp_w + del_w * ncols
    row_h   = 7*mm
    name_max = 18  # chars per line in header (simple trim)

    # Header block (business name above course reference)
    y = top
    c.setFont("Helvetica-Bold", 14)
    c.drawString(left, y, f"{booking.course_type.name} — Assessment Matrix")
    y -= 6*mm
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Business: {booking.business.name}")
    y -= 5*mm
    c.drawString(left, y, f"Course reference: {booking.course_reference or '—'}")
    y -= 5*mm
    c.drawString(left, y, f"Instructor: {booking.instructor.name if booking.instructor else '—'}")
    y -= 5*mm
    c.drawString(left, y, f"Course dates: {format_course_dates(day_dates)}")
    y -= 7*mm

    def draw_header_row():
        """Draw the competency/delegate header row at current y."""
        nonlocal y
        # Light fill for entire header band
        c.setFillGray(0.95)
        c.rect(left, y - header_h, table_w, header_h, stroke=0, fill=1)
        c.setFillGray(0)

        c.setFont("Helvetica-Bold", 9)
        # Competency header cell
        c.rect(left, y - header_h, comp_w, header_h, stroke=1, fill=0)
        c.drawCentredString(left + comp_w/2, y - header_h + 4.5*mm, "Competency")

        # Delegate header cells (rotated names)
        x = left + comp_w
        for d in delegates:
            c.rect(x, y - header_h, del_w, header_h, stroke=1, fill=0)
            c.saveState()
            try:
                c.translate(x + del_w/2, y - header_h/2)
                c.rotate(90)
                c.setFont("Helvetica-Bold", name_fs)  # bold helps legibility
                parts = (d.name or "").split()
                first = (parts[0] if parts else "")[:name_max]
                last  = (" ".join(parts[1:]) if len(parts) > 1 else "")[:name_max]
                c.drawCentredString(0, -3.2*mm, first)
                if last:
                    c.drawCentredString(0, +3.2*mm, last)
            finally:
                c.restoreState()
            x += del_w

        y -= header_h
        c.setFont("Helvetica", 9)

    def new_page(continued=False):
        """End current page with footer, start a new page, redraw header row."""
        nonlocal y
        # Finish previous page with footer
        draw_footer()
        c.showPage()
        # New page header
        y = H - 15*mm
        c.setFont("Helvetica-Bold", 14)
        title = f"{booking.course_type.name} — Assessment Matrix"
        if continued:
            title += " (cont.)"
        c.drawString(left, y, title)
        y -= 6*mm
        c.setFont("Helvetica", 10)
        c.drawString(left, y, f"Business: {booking.business.name}")
        y -= 5*mm
        c.drawString(left, y, f"Course reference: {booking.course_reference or '—'}")
        y -= 5*mm
        c.drawString(left, y, f"Instructor: {booking.instructor.name if booking.instructor else '—'}")
        y -= 5*mm
        c.drawString(left, y, f"Course dates: {format_course_dates(day_dates)}")
        y -= 7*mm
        draw_header_row()

    # First header
    draw_header_row()

    # Body with darker zebra striping
    check_mark = "✔"
    cross_mark = "—"

    for idx, comp in enumerate(competencies, start=1):
        if y - row_h < bottom + 25*mm:
            new_page(continued=True)

        # darker zebra band (behind grid)
        if idx % 2 == 0:
            c.setFillGray(0.86)
            c.rect(left, y - row_h, table_w, row_h, stroke=0, fill=1)
            c.setFillGray(0)

        # competency name cell
        c.rect(left, y - row_h, comp_w, row_h, stroke=1, fill=0)
        c.setFont("Helvetica", 9)
        c.drawString(left + 2*mm, y - row_h + 2.2*mm, (comp.name or "")[:80])

        # per-delegate cells
        x = left + comp_w
        for d in delegates:
            c.rect(x, y - row_h, del_w, row_h, stroke=1, fill=0)
            lvl = assess_map.get((d.id, comp.id))
            ok = (lvl in ("c", "e"))
            c.setFont("Helvetica-Bold", 10 if ok else 9)
            c.drawCentredString(x + del_w/2, y - row_h + 2*mm, check_mark if ok else cross_mark)
            x += del_w

        y -= row_h

    # Outcome row
    if y - 9*mm < bottom + 15*mm:
        new_page(continued=True)
    c.setFont("Helvetica-Bold", 9)
    c.setFillGray(0.94)
    c.rect(left, y - 9*mm, table_w, 9*mm, stroke=0, fill=1)
    c.setFillGray(0)
    c.rect(left, y - 9*mm, comp_w, 9*mm, stroke=1, fill=0)
    c.drawString(left + 2*mm, y - 7*mm, "Outcome")
    x = left + comp_w
    for d in delegates:
        c.rect(x, y - 9*mm, del_w, 9*mm, stroke=1, fill=0)
        status = (d.outcome or "").upper()
        colour = {
            "PASS": (0, 130/255, 84/255),
            "FAIL": (180/255, 0, 0),
            "DNF":  (170/255, 120/255, 0),
        }.get(status, (0, 0, 0))
        c.setFillColorRGB(*colour)
        c.drawCentredString(x + del_w/2, y - 7*mm, status or "—")
        c.setFillColorRGB(0, 0, 0)
        x += del_w
    y -= 12*mm

    # Legend / footer (last page)
    c.setFont("Helvetica", 8)
    c.drawString(left, y, f"Legend: {check_mark} competent / — competency not demonstrated; Outcome colours: Pass (green), Fail (red), DNF (amber).")
    y -= 6*mm
    c.drawString(left, y, f"Business: {booking.business.name}")

    # Footer on last page, save
    draw_footer()
    c.save()
    buf.seek(0)
    filename = f"assessments_{booking.course_reference or booking.pk}.pdf"
    return FileResponse(buf, as_attachment=True, filename=filename)

import io
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Max, Avg, Q
from django.forms import modelformset_factory
from django.http import JsonResponse, HttpResponseForbidden, FileResponse, HttpResponseNotAllowed, HttpResponse, Http404
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from io import BytesIO
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from statistics import mean

from .models import Instructor, Booking, BookingDay, DelegateRegister, CourseCompetency, FeedbackResponse
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
    """
    Instructor course detail with:
      - day list and delegate counts
      - notes form
      - assessments context (if available)
      - feedback tab context (responses for the booking's dates + course type)
    """
    instr = getattr(request.user, "instructor", None)
    booking = get_object_or_404(
        Booking.objects.select_related("course_type", "business", "instructor", "training_location"),
        pk=pk,
    )

    # Only the assigned instructor may view
    if not instr or booking.instructor_id != instr.id:
        messages.error(request, "You do not have access to this booking.")
        return redirect("instructor_bookings")

    # Notes form
    if request.method == "POST":
        notes_form = BookingNotesForm(request.POST, instance=booking)
        if notes_form.is_valid():
            notes_form.save()
            messages.success(request, "Course notes saved.")
            return redirect("instructor_booking_detail", pk=booking.pk)
    else:
        notes_form = BookingNotesForm(instance=booking)

    # Course days summary
    days_qs = (
        BookingDay.objects
        .filter(booking=booking)
        .order_by("date")
        .annotate(n=Count("delegateregister"))
    )
    day_rows = [{
        "id": d.id,
        "date": date_format(d.date, "j M Y"),
        "start_time": d.start_time,
        "n": d.n or 0,
        "edit_url": redirect("instructor_day_registers", pk=d.id).url,
    } for d in days_qs]

    # Feedback responses for this booking: same course type AND date is one of the booking's days
    booking_dates = list(days_qs.values_list("date", flat=True))
    if booking_dates:
        fb_qs = (
            FeedbackResponse.objects
            .filter(
                course_type_id=booking.course_type_id,
                date__in=booking_dates,
                instructor_id=booking.instructor_id,   # ← restrict to this booking's instructor
            )
            .order_by("-date", "-created_at")
        )
    else:
        fb_qs = FeedbackResponse.objects.none()

    fb_count = fb_qs.count()
    fb_avg = fb_qs.aggregate(avg=Avg("overall_rating"))["avg"]

    ctx = {
        "title": booking.course_type.name,
        "booking": booking,
        "day_rows": day_rows,
        "back_url": redirect("instructor_bookings").url,
        "notes_form": notes_form,
        "has_exam": getattr(booking.course_type, "has_exam", False),

        # Feedback tab context
        "fb_qs": fb_qs,
        "fb_count": fb_count,
        "fb_avg": fb_avg,
    }

    # Assessment context (best-effort)
    try:
        ctx.update(_assessment_context(booking, request.user))  # if you have this helper
    except Exception:
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

# views_instructor.py
from django.db.models import Avg, Count
# ...existing imports...
from .models import FeedbackResponse

def instructor_feedback_tab(request, booking_id):
    """
    Feedback tab for a booking:
    - lists individual forms (date, instructor, overall)
    - shows quick summary stats
    """
    booking = get_object_or_404(Booking, pk=booking_id)

    # Full date range for this booking (min..max across all days)
    day_qs = booking.days.order_by("date").values_list("date", flat=True)
    if day_qs:
        start_date = day_qs.first()
        end_date   = day_qs.last()
        date_filter = {"date__range": (start_date, end_date)}
    else:
        # fall back to the booking start date if no days are present
        start_date = end_date = booking.course_date
        date_filter = {"date": booking.course_date}

    # Pull responses for this booking's course_type and date range
    qs = (
        FeedbackResponse.objects
        .filter(course_type=booking.course_type, **date_filter)
        .select_related("instructor")
        .order_by("-date", "-created_at")
    )

    summary = qs.aggregate(n=Count("id"), avg_overall=Avg("overall_rating"))

    context = {
        "title": "Feedback",
        "booking": booking,
        "responses": qs,
        "summary": summary,
    }
    return render(request, "instructor/booking_feedback.html", context)



def instructor_feedback_view(request, pk):
    """
    Read-only view of a single feedback response.
    """
    fb = get_object_or_404(FeedbackResponse.objects.select_related("course_type", "instructor"), pk=pk)
    return render(request, "instructor/feedback_detail.html", {"fb": fb})

@login_required
def instructor_feedback_all_pdf(request, pk):
    # simple redirect to a public/export endpoint if you already have one
    return redirect("public_feedback_pdf", pk=pk)  # or build your own combined PDF

@login_required
def instructor_feedback_summary_pdf(request, pk):
    # generate a 1-page summary; can reuse ReportLab similar to your matrix/export
    # (left as a stub so we don’t collide with existing code)
    return HttpResponseNotAllowed(["GET"])

def _feedback_queryset_for_booking(booking):
    day_qs = booking.days.order_by("date").values_list("date", flat=True)
    if day_qs:
        start_date, end_date = day_qs.first(), day_qs.last()
        date_filter = {"date__range": (start_date, end_date)}
    else:
        start_date = end_date = booking.course_date
        date_filter = {"date": booking.course_date}

    return (
        FeedbackResponse.objects
        .filter(course_type=booking.course_type, **date_filter)
        .select_related("instructor")
        .order_by("date", "created_at")
    )

def _pdf_header_footer(c, booking, title):
    w, h = A4
    c.setTitle(title)

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20*mm, h - 20*mm, f"{booking.course_type.name} — {title}")
    c.setFont("Helvetica", 10)
    c.drawString(20*mm, h - 26*mm, f"Course reference: {booking.course_reference}")
    c.drawString(20*mm, h - 31*mm, f"Business: {booking.business.name}")
    # Dates line
    day_qs = booking.days.order_by("date").values_list("date", flat=True)
    if day_qs:
        ds = day_qs.first().strftime("%d %b %Y")
        de = day_qs.last().strftime("%d %b %Y")
        date_str = ds if ds == de else f"{ds} – {de}"
    else:
        date_str = booking.course_date.strftime("%d %b %Y")
    c.drawString(20*mm, h - 36*mm, f"Course dates: {date_str}")

    # Footer
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.grey)
    c.drawString(20*mm, 10*mm, "Unicorn Fire & Safety Solutions, Unicorn House, 6 Salendine, Shrewsbury, SY1 3XJ · info@unicornsafety.co.uk · 01743 360211")
    c.setFillColor(colors.black)

@login_required
def instructor_feedback_pdf_all(request, booking_id):
    """
    Export all individual feedback forms for THIS booking (portrait).
    Filters by:
      - booking.course_type
      - dates within the booking's days (or booking.course_date)
      - instructor == booking.instructor
    """
    instr = getattr(request.user, "instructor", None)
    booking = get_object_or_404(
        Booking.objects.select_related("course_type", "business", "instructor"),
        pk=booking_id,
    )
    if not instr or booking.instructor_id != instr.id:
        return HttpResponseForbidden("You do not have access to this booking.")

    # Date window = all booking days (fallback to booking.course_date)
    day_dates = list(
        BookingDay.objects.filter(booking=booking)
        .order_by("date").values_list("date", flat=True)
    )
    if day_dates:
        date_min, date_max = min(day_dates), max(day_dates)
    else:
        date_min = date_max = booking.course_date

    # *** KEY FILTER: restrict to this booking's instructor ***
    responses = list(
        FeedbackResponse.objects.filter(
            course_type=booking.course_type,
            instructor_id=booking.instructor_id,
            date__gte=date_min,
            date__lte=date_max,
        ).select_related("instructor")
         .order_by("created_at", "id")
    )

    # ---------- PDF ----------
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)   # portrait
    W, H = A4

    M_L = 18*mm; M_R = 18*mm; M_T = 16*mm; M_B = 16*mm
    left, right, top, bottom = M_L, W - M_R, H - M_T, M_B
    content_w = right - left

    from reportlab.pdfbase import pdfmetrics
    def sw(txt, font="Helvetica", size=10):
        return pdfmetrics.stringWidth(str(txt), font, size)

    def wrap_lines(text, font="Helvetica", size=9.5, max_width=120*mm):
        text = (text or "").replace("\r", " ").strip()
        if not text:
            return []
        words, lines, cur = text.split(), [], ""
        for w in words:
            probe = (cur + " " + w).strip()
            if sw(probe, font, size) <= max_width:
                cur = probe
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        return lines

    def header():
        y = top
        c.setFont("Helvetica-Bold", 14)
        c.drawString(left, y, f"{booking.course_type.name} — Feedback — All Forms")
        y -= 7*mm
        c.setFont("Helvetica", 10)
        meta = [
            ("Course reference", booking.course_reference or "—"),
            ("Business", booking.business.name),
            ("Course dates", _format_course_dates_for_booking(booking)),
            ("Instructor", booking.instructor.name if booking.instructor else "—"),
        ]
        for k, v in meta:
            c.setFont("Helvetica-Bold", 10);  c.drawString(left, y, f"{k}:")
            c.setFont("Helvetica", 10);       c.drawString(left+35*mm, y, str(v))
            y -= 4.8*mm
        c.setStrokeColorRGB(.8,.8,.85)
        c.line(left, y-1.5*mm, right, y-1.5*mm)
        c.setStrokeColor(colors.black)
        return y - 5*mm

    def footer():
        c.setFont("Helvetica", 8.5)
        c.setFillColorRGB(0.35, 0.35, 0.4)
        c.drawCentredString(
            W/2, 8*mm,
            "Unicorn Fire & Safety Solutions, Unicorn House, 6 Salendine, Shrewsbury, SY1 3XJ  ·  info@unicornsafety.co.uk  ·  01743 360211"
        )
        c.setFillColor(colors.black)

    def draw_card(y, idx, r):
        pad = 5*mm
        col_gap = 6*mm
        col1_x = left + pad + 1*mm
        col2_x = left + pad + 70*mm
        usable_w = content_w - 2*pad

        short_rows = 5
        line_h = 4.9*mm
        comment_lines = wrap_lines(r.comments, "Helvetica-Oblique", 9.5, max_width=usable_w-6*mm)
        comment_h = (len(comment_lines) or 1) * line_h
        cb_needed = 1 if getattr(r, "wants_callback", False) else 0
        cb_h = cb_needed * line_h
        title_h = 7*mm

        need = title_h + 2*mm + short_rows*line_h + 2*mm + line_h*2 + 2*mm + comment_h + cb_h + 4*mm
        if y - need < bottom + 20*mm:
            c.showPage()
            y = header()

        c.setFillColorRGB(0.97, 0.98, 1.0)
        c.setStrokeColorRGB(0.85, 0.88, 0.95)
        c.roundRect(left, y-need, content_w, need, 3*mm, fill=1, stroke=1)
        c.setFillColor(colors.black); c.setStrokeColor(colors.black)

        cy = y - pad
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left+pad, cy-4*mm, f"{idx}. {r.date.strftime('%d %b %Y')}")
        c.setFont("Helvetica", 10)
        c.drawString(left+pad+40*mm, cy-4*mm, f"Instructor: {r.instructor.name if r.instructor else '—'}")
        c.setFont("Helvetica-Bold", 10)
        ov = getattr(r, "overall_rating", None)
        c.drawRightString(right-pad, cy-4*mm, f"Overall: {ov}/5" if ov else "Overall: —")
        cy -= (title_h + 2*mm)

        c.setFont("Helvetica", 9.5)
        col1 = [
            ("Prior knowledge", r.prior_knowledge),
            ("Post", r.post_knowledge),
            ("Structure", r.q_structure),
            ("Pace", r.q_pace),
            ("Materials", r.q_materials_quality),
        ]
        col2 = [
            ("Purpose clear", r.q_purpose_clear),
            ("Met needs", r.q_personal_needs),
            ("Content clear", r.q_content_clear),
            ("Instructor knowledge", r.q_instructor_knowledge),
            ("Books/handouts", r.q_books_quality),
        ]
        for i in range(short_rows):
            c.drawString(col1_x, cy, f"{col1[i][0]}: {col1[i][1] if col1[i][1] else '—'}")
            c.drawString(col2_x, cy, f"{col2[i][0]}: {col2[i][1] if col2[i][1] else '—'}")
            cy -= line_h

        c.drawString(col1_x, cy, f"Venue: {r.q_venue_suitable if r.q_venue_suitable else '—'}")
        c.drawString(col2_x, cy, f"Work benefit: {r.q_benefit_at_work if r.q_benefit_at_work else '—'}")
        cy -= line_h
        c.drawString(col1_x, cy, f"Outside-work benefit: {r.q_benefit_outside if r.q_benefit_outside else '—'}")
        cy -= (line_h + 1*mm)

        c.setFont("Helvetica-Bold", 10)
        c.drawString(col1_x, cy, "Comments:")
        cy -= line_h
        c.setFont("Helvetica-Oblique", 9.5)
        if comment_lines:
            for ln in comment_lines:
                c.drawString(col1_x+6*mm, cy, ln)
                cy -= line_h
        else:
            c.drawString(col1_x+6*mm, cy, "—")
            cy -= line_h

        if cb_needed:
            c.setFont("Helvetica-Bold", 9.5)
            c.setFillColorRGB(0.8, 0.1, 0.1)
            c.drawString(col1_x, cy, "Requested a callback")
            c.setFillColor(colors.black)
            c.setFont("Helvetica", 9.5)
            c.drawString(col1_x + 42*mm, cy, f"Name: {(r.contact_name or '—').strip()}")
            c.drawString(col1_x + 95*mm, cy, f"Email: {(r.contact_email or '—').strip()}")
            c.drawString(col1_x + 150*mm, cy, f"Tel: {(r.contact_phone or '—').strip()}")
            cy -= line_h

        return (y - need) - 6*mm

    y = header()
    if not responses:
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(left, y, "No feedback responses yet for this booking.")
    else:
        for i, r in enumerate(responses, start=1):
            y = draw_card(y, i, r)

    footer(); c.showPage(); footer(); c.save()
    buf.seek(0)
    filename = f"feedback_all_{booking.course_reference or booking.pk}.pdf"
    return FileResponse(buf, as_attachment=True, filename=filename)



# --- ADD these two helpers (near your other helpers) ---
def _format_course_dates_for_booking(booking):
    """Return a nice dates string across all BookingDay rows."""
    days = list(BookingDay.objects.filter(booking=booking).order_by("date").values_list("date", flat=True))
    if not days:
        return booking.course_date.strftime("%d %b %Y")
    if len(days) == 1:
        return days[0].strftime("%d %b %Y")
    return f"{days[0].strftime('%d %b %Y')} – {days[-1].strftime('%d %b %Y')}"

def _draw_zebra_row(c, x, y, w, h, idx, light=0.96, dark=0.90):
    """Subtle zebra background behind a row rectangle at (x,y)."""
    col = colors.Color(dark, dark, dark) if (idx % 2) else colors.Color(light, light, light)
    c.setFillColor(col)
    c.setStrokeColor(col)
    c.rect(x, y, w, h, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)

# --- REPLACE your current instructor_feedback_pdf_summary with this one ---
@login_required
def instructor_feedback_pdf_summary(request, booking_id):
    """
    Pretty PDF summary (landscape) for THIS booking.
    Filters by course_type, booking day range, and booking.instructor.
    """
    instr = getattr(request.user, "instructor", None)
    booking = get_object_or_404(
        Booking.objects.select_related("course_type", "business", "instructor"),
        pk=booking_id,
    )
    if not instr or booking.instructor_id != instr.id:
        return HttpResponseForbidden("You do not have access to this booking.")

    # Date window
    day_dates = list(
        BookingDay.objects.filter(booking=booking).order_by("date").values_list("date", flat=True)
    )
    if day_dates:
        date_min, date_max = min(day_dates), max(day_dates)
    else:
        date_min = date_max = booking.course_date

    # *** KEY FILTER: restrict to this booking's instructor ***
    responses = list(
        FeedbackResponse.objects.filter(
            course_type=booking.course_type,
            instructor_id=booking.instructor_id,
            date__gte=date_min,
            date__lte=date_max,
        ).order_by("created_at", "id")
    )

    # Aggregates
    count = len(responses)
    vals = [int(r.overall_rating) for r in responses if getattr(r, "overall_rating", None)]
    overall_avg = round(mean(vals), 2) if vals else None
    dist = {i: 0 for i in range(1, 6)}
    for v in vals:
        if 1 <= v <= 5:
            dist[v] += 1

    score_fields = [
        ("Prior knowledge", "prior_knowledge"),
        ("Post knowledge", "post_knowledge"),
        ("Purpose & objectives clear", "q_purpose_clear"),
        ("Met my training needs", "q_personal_needs"),
        ("Exercises were useful", "q_exercises_useful"),
        ("Structure / logical", "q_structure"),
        ("Pace suitable", "q_pace"),
        ("Content & language clear", "q_content_clear"),
        ("Instructor knowledgeable", "q_instructor_knowledge"),
        ("Materials / equipment quality", "q_materials_quality"),
        ("Books / handouts quality", "q_books_quality"),
        ("Venue suitable & comfortable", "q_venue_suitable"),
        ("Beneficial at work", "q_benefit_at_work"),
        ("Beneficial outside work", "q_benefit_outside"),
    ]
    def avg_of(field):
        nums = []
        for r in responses:
            v = getattr(r, field, None)
            try:
                v = int(v)
            except Exception:
                v = None
            if v and 1 <= v <= 5:
                nums.append(v)
        return round(mean(nums), 2) if nums else None
    averages = [(label, avg_of(attr)) for (label, attr) in score_fields]

    comments = [r.comments.strip() for r in responses if (r.comments or "").strip()]
    callbacks = [
        {
            "name": (r.contact_name or "").strip() or "—",
            "email": (r.contact_email or "").strip(),
            "phone": (r.contact_phone or "").strip(),
            "submitted": r.created_at,
        }
        for r in responses if getattr(r, "wants_callback", False)
    ]

    # ---------- PDF ----------
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A4))
    W, H = landscape(A4)

    left = 18*mm; right = W - 18*mm; top = H - 16*mm; bottom = 14*mm
    width = right - left

    def draw_header():
        y = top
        c.setFont("Helvetica-Bold", 14)
        c.drawString(left, y, "Course Feedback — Summary")
        y -= 7*mm
        c.setFont("Helvetica", 10)
        meta = [
            ("Business", booking.business.name),
            ("Course", booking.course_type.name),
            ("Reference", booking.course_reference or "—"),
            ("Dates", _format_course_dates_for_booking(booking)),
            ("Instructor", booking.instructor.name if booking.instructor else "—"),
            ("Responses", str(count)),
        ]
        col_gap = 8*mm
        col_w = (width - col_gap) / 2
        x1, x2 = left, left + col_w + col_gap
        y1 = y2 = y
        for i, (k, v) in enumerate(meta[:3]):
            c.setFont("Helvetica-Bold", 10); c.drawString(x1, y1, f"{k}:")
            c.setFont("Helvetica", 10);      c.drawString(x1+28*mm, y1, str(v)); y1 -= 5.2*mm
        for i, (k, v) in enumerate(meta[3:]):
            c.setFont("Helvetica-Bold", 10); c.drawString(x2, y2, f"{k}:")
            c.setFont("Helvetica", 10);      c.drawString(x2+28*mm, y2, str(v)); y2 -= 5.2*mm
        yy = min(y1, y2)
        c.setStrokeColorRGB(.8,.8,.85); c.line(left, yy-2*mm, right, yy-2*mm); c.setStrokeColor(colors.black)
        return yy - 6*mm

    def draw_overall(y):
        c.setFont("Helvetica-Bold", 12); c.drawString(left, y, "Overall rating")
        if overall_avg is None:
            c.setFont("Helvetica", 10); c.drawString(left + 45*mm, y, "No responses")
            return y - 10*mm
        # avg badge
        badge_h, badge_w = 12*mm, 28*mm
        x_badge, y_badge = left + 45*mm, y + 3*mm - badge_h
        c.setFillColorRGB(0.89, 0.96, 0.90); c.setStrokeColorRGB(0.75, 0.90, 0.80)
        c.roundRect(x_badge, y_badge, badge_w, badge_h, 2.5*mm, stroke=1, fill=1)
        c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(x_badge + badge_w/2, y_badge + 3.2*mm, f"{overall_avg:.2f}")
        # distribution
        c.setFont("Helvetica", 10); x = x_badge + badge_w + 10*mm; c.drawString(x, y, "Distribution:")
        x += 24*mm
        for i in range(1, 6):
            c.drawString(x, y, f"{i}: {dist.get(i,0)}"); x += 18*mm
        return y - 10*mm

    def zebra(y, idx, h):  # subtle background
        col = 0.96 if idx % 2 else 0.90
        c.setFillColorRGB(col, col, col); c.rect(left, y-h+2, width, h-2, stroke=0, fill=1); c.setFillColor(colors.black)

    def draw_averages(y):
        c.setFont("Helvetica-Bold", 12); c.drawString(left, y, "Averages by question"); y -= 5*mm
        row_h = 7*mm
        for i, (label, avgv) in enumerate(averages, start=1):
            if y - row_h < bottom + 40*mm:
                c.showPage(); y = draw_header()
                c.setFont("Helvetica-Bold", 12); c.drawString(left, y, "Averages by question (cont.)"); y -= 7*mm
            zebra(y, i, row_h)
            c.setFont("Helvetica", 9.5); c.drawString(left + 1.5*mm, y - 4.8*mm, label)
            c.setFont("Helvetica-Bold", 10)
            c.drawRightString(right - 1.5*mm, y - 4.8*mm, ("—" if avgv is None else f"{avgv:.2f}"))
            y -= row_h
        return y - 6*mm

    def draw_comments(y):
        if not comments: return y
        c.setFont("Helvetica-Bold", 12); c.drawString(left, y, "Comments"); y -= 6*mm
        row_h = 12*mm
        for i, txt in enumerate(comments, start=1):
            s = " ".join(txt.replace("\r", "").splitlines()).strip()
            chunks = []
            while len(s) > 110:
                cut = s.rfind(" ", 0, 110); cut = 110 if cut <= 0 else cut
                chunks.append(s[:cut].strip()); s = s[cut:].strip()
            if s: chunks.append(s)
            need = max(row_h, 5*mm + len(chunks)*5.2*mm)
            if y - need < bottom + 16*mm:
                c.showPage(); y = draw_header()
                c.setFont("Helvetica-Bold", 12); c.drawString(left, y, "Comments (cont.)"); y -= 6*mm
            zebra(y, i, need)
            c.setFont("Helvetica-Oblique", 9.5)
            yy = y - 6*mm
            for line in chunks:
                c.drawString(left + 2*mm, yy, f"“{line}”"); yy -= 5.2*mm
            y -= need
        return y - 4*mm

    def draw_callbacks(y):
        if not callbacks: return y
        c.setFont("Helvetica-Bold", 12); c.drawString(left, y, "Call-back requested"); y -= 6*mm
        row_h = 7.2*mm
        widths = [50*mm, 60*mm, 40*mm, width - (50+60+40)*mm]
        xs = [left, left+widths[0], left+widths[0]+widths[1], left+widths[0]+widths[1]+widths[2]]
        # header
        zebra(y, 0, row_h)
        c.setFont("Helvetica-Bold", 10)
        for i, htxt in enumerate(["Name", "Email", "Telephone", "Submitted"]):
            c.drawString(xs[i] + 1.5*mm, y - 4.5*mm, htxt)
        y -= row_h; c.setFont("Helvetica", 9.5)
        for i, cb in enumerate(callbacks, start=1):
            if y - row_h < bottom + 16*mm:
                c.showPage(); y = draw_header()
                c.setFont("Helvetica-Bold", 12); c.drawString(left, y, "Call-back requested (cont.)"); y -= 6*mm
                zebra(y, 0, row_h); c.setFont("Helvetica-Bold", 10)
                for j, htxt in enumerate(["Name", "Email", "Telephone", "Submitted"]):
                    c.drawString(xs[j] + 1.5*mm, y - 4.5*mm, htxt)
                y -= row_h; c.setFont("Helvetica", 9.5)
            zebra(y, i, row_h)
            c.drawString(xs[0] + 1.5*mm, y - 4.5*mm, cb["name"] or "—")
            c.drawString(xs[1] + 1.5*mm, y - 4.5*mm, cb["email"] or "—")
            c.drawString(xs[2] + 1.5*mm, y - 4.5*mm, cb["phone"] or "—")
            submitted = cb["submitted"].strftime("%d %b %Y %H:%M") if cb.get("submitted") else "—"
            c.drawString(xs[3] + 1.5*mm, y - 4.5*mm, submitted)
            y -= row_h
        return y - 4*mm

    def footer():
        c.setFont("Helvetica", 8.5)
        c.setFillColorRGB(0.35, 0.35, 0.4)
        c.drawCentredString(W/2, 8*mm,
            "Unicorn Fire & Safety Solutions, Unicorn House, 6 Salendine, Shrewsbury, SY1 3XJ  ·  info@unicornsafety.co.uk  ·  01743 360211")
        c.setFillColor(colors.black)

    y = draw_header()
    y = draw_overall(y)
    y = draw_averages(y)
    y = draw_comments(y)
    y = draw_callbacks(y)
    footer(); c.showPage(); footer(); c.save()

    buf.seek(0)
    filename = f"feedback_summary_{booking.course_reference or booking.pk}.pdf"
    return FileResponse(buf, as_attachment=True, filename=filename)

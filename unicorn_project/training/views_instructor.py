import io
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.forms import modelformset_factory
from django.http import JsonResponse, HttpResponseForbidden, FileResponse, HttpResponseNotAllowed
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

from .models import Instructor, Booking, BookingDay, DelegateRegister
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

    return render(request, "instructor/booking_detail.html", {
        "title": booking.course_type.name,
        "booking": booking,
        "day_rows": day_rows,
        "back_url": redirect("instructor_bookings").url,
        "notes_form": notes_form,   # <-- make sure this is present
    })



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
    Generate a simple PDF for a day's register (delegates list), in LANDSCAPE.
    """
    instr = getattr(request.user, "instructor", None)
    day = get_object_or_404(
        BookingDay.objects.select_related("booking__course_type", "booking__business", "booking__instructor"),
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

    buffer = io.BytesIO()

    # --- LANDSCAPE here ---
    pagesize = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=pagesize)
    W, H = pagesize

    # Margins and helpers
    left = 20 * mm
    right = W - 20 * mm
    top = H - 20 * mm
    line_h = 7 * mm

    def draw_line(x1, y1, x2, y2):
        c.line(x1, y1, x2, y2)

    def draw_page_header(cont=False):
        y = top
        c.setFont("Helvetica-Bold", 14)
        title = f"{day.booking.course_type.name} — Register"
        if cont:
            title += " (cont.)"
        c.drawString(left, y, title)
        y -= 10 * mm
        c.setFont("Helvetica", 10)
        c.drawString(left, y, f"Date: {day.date.strftime('%d %b %Y')}")
        y -= 5 * mm
        c.drawString(left, y, f"Business: {day.booking.business.name}")
        y -= 5 * mm
        c.drawString(left, y, f"Instructor: {day.booking.instructor.name}")
        y -= 8 * mm
        draw_line(left, y, right, y)
        y -= 5 * mm
        # Column headers
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left, y, "Name")
        c.drawString(left + 60*mm, y, "DOB")
        c.drawString(left + 85*mm, y, "Job title")
        c.drawString(left + 135*mm, y, "Emp. ID")
        y -= 5 * mm
        draw_line(left, y, right, y)
        y -= 3 * mm
        c.setFont("Helvetica", 10)
        return y

    y = draw_page_header(cont=False)

    for r in regs:
        # If near bottom, new page + header again
        if y < 30 * mm:
            c.showPage()
            y = draw_page_header(cont=True)

        dob = r.date_of_birth.strftime("%d/%m/%Y") if r.date_of_birth else "—"
        c.drawString(left, y, r.name or "—")
        c.drawString(left + 60*mm, y, dob)
        c.drawString(left + 85*mm, y, (r.job_title or "—")[:40])
        c.drawString(left + 135*mm, y, r.employee_id or "—")
        y -= line_h

        if r.notes:
            txt = f"Notes: {r.notes}"
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(left + 10*mm, y, txt[:120])  # light wrapping
            c.setFont("Helvetica", 10)
            y -= 5 * mm

    # IMPORTANT: do NOT call c.showPage() here, or you'll get a blank last page.
    c.save()
    buffer.seek(0)
    filename = f"register_{day.date.strftime('%Y%m%d')}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename)
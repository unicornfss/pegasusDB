from pathlib import Path
import io, smtplib, ssl, contextlib
import os
from decimal import Decimal
from datetime import timedelta, datetime
from django.contrib import messages
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Count, Max, Avg, Q
from django.forms import modelformset_factory
from django.http import JsonResponse, HttpResponseForbidden, FileResponse, HttpResponseNotAllowed, HttpResponse, Http404, HttpResponseServerError
from django.shortcuts import redirect, render, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.timezone import now
from .utils.invoice_html import render_invoice_pdf_from_html, resolve_admin_email
from .utils.course_docs import email_all_course_docs_to_admin

from io import BytesIO
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from statistics import mean

import subprocess, tempfile, os

from .models import Instructor, Booking, BookingDay, DelegateRegister, CourseCompetency, FeedbackResponse, Invoice, InvoiceItem
from .forms import DelegateRegisterInstructorForm, BookingNotesForm

from .utils.invoice import (
    get_invoice_template_path,
    render_invoice_pdf,      # returns (bytes, filename); falls back to DOCX if PDF conversion not available
    render_invoice_file,     # if you want to choose prefer_pdf=False somewhere
    send_invoice_email,      # email helper with dev/admin routing
)

def get_invoice_template_path():
    """
    Find Invoice.docx in common locations (project-level templates or app templates).
    """
    candidates = [
        Path(settings.BASE_DIR) / "templates" / "invoicing" / "Invoice.docx",
        Path(settings.BASE_DIR) / "unicorn_project" / "training" / "templates" / "invoicing" / "Invoice.docx",
        Path(__file__).resolve().parent / "templates" / "invoicing" / "Invoice.docx",
    ]
    for p in candidates:
        try:
            if p.exists():
                return str(p)
        except Exception:
            pass
    raise FileNotFoundError("Invoice.docx template not found. Tried: " + " | ".join(str(p) for p in candidates))

# Adjust if your templates dir differs
DOCX_TEMPLATE_PATH = os.path.join(settings.BASE_DIR, "templates", "invoicing", "Invoice.docx")

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



def _invoicing_tab_context(booking):
    """Build context keys that _invoicing_tab.html expects."""
    inv = _get_or_create_invoice(booking)
    instr = booking.instructor

    inv_date = inv.invoice_date or now().date()

    try:
        base_fee = booking.instructor_fee
        if base_fee in (None, ""):
            base_fee = getattr(booking.course_type, "default_instructor_fee", 0)
    except Exception:
        base_fee = 0

    bank_name = (inv.account_name or (getattr(instr, "name_on_account", "") if instr else "") or "")
    bank_sort = (inv.sort_code or (getattr(instr, "bank_sort_code", "") if instr else "") or "")
    bank_num  = (inv.account_number or (getattr(instr, "bank_account_number", "") if instr else "") or "")

    addr_parts = []
    if instr:
        for f in ["address_line", "town", "postcode"]:
            addr_parts.append(getattr(instr, f, "") or "")
    instructor_address = ", ".join([x for x in addr_parts if x.strip()])

    return {
        "invoice": inv,
        "invoice_date": inv_date,
        "base_instructor_fee": base_fee or 0,
        "invoice_items": list(getattr(inv, "items", []).all()) if hasattr(inv, "items") else [],
        "bank_account_name": bank_name,
        "bank_sort_code": bank_sort,
        "bank_account_number": bank_num,
        "instructor_address": instructor_address or "—",
    }

@login_required
def instructor_bookings(request):
    """
    Instructor’s bookings dashboard.
    """
    inst = _get_instructor(request.user)
    if not inst:
        messages.error(request, "Your user account isn’t linked to an instructor record.")
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

    # --- CLOSED (completed/closed) ---
    closed_qs = (
        base_qs.filter(status__in=["completed", "closed"])
        .order_by("-course_date", "-id")
    )
    closed_total = closed_qs.count()

    p = Paginator(closed_qs, 10)
    closed_page = p.get_page(request.GET.get("closed_page") or 1)

    # Copy the page’s rows so we can annotate them
    closed_rows = list(closed_page.object_list)

    # Map of booking_id -> invoice status
    inv_map = {
        inv.booking_id: (inv.status or "").lower()
        for inv in Invoice.objects.filter(booking_id__in=[b.id for b in closed_rows])
    }

    # Attach invoice_status directly to each booking row
    for b in closed_rows:
        b.invoice_status = inv_map.get(b.id, "")

    # Simple list fallback (first page items) for older templates
    closed = list(closed_qs[:10])

    return render(request, "instructor/bookings.html", {
        "title": "My bookings",
        "instructor": inst,
        "in_progress": in_progress,
        "awaiting": awaiting,
        "scheduled": scheduled,
        "closed_page": closed_page,
        "closed_rows": closed_rows,      # <— use this for rendering closed rows
        "closed_total": closed_total,    # <— correct badge count
        "closed": closed,                 # fallback if needed
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

def _unique_delegates_for_booking(booking):
    """
    Return DelegateRegister rows for the booking, deduped by (normalized name, DOB).
    Keep the first occurrence (lowest id). If DOB is missing, do NOT dedupe that row.
    """
    qs = (
        DelegateRegister.objects
        .filter(booking_day__booking=booking)
        .order_by("name", "date_of_birth", "id")
        # IMPORTANT: no select_related here; and avoid deferring fields needed by FK traversal
        # (we don't actually traverse booking_day in this helper)
        # If you want to keep 'only', include booking_day_id to be safe:
        # .only("id", "name", "date_of_birth", "outcome", "booking_day_id")
    )

    unique = []
    seen = set()
    for r in qs:
        nm = (r.name or "").strip().lower()
        dob = getattr(r, "date_of_birth", None)
        key = (nm, dob) if dob else ("__nodedob__", r.id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique



def _assessment_context(booking, user):
    # permissions: staff or assigned instructor (match the guard used in the view)
    instr = getattr(user, "instructor", None)
    if not (user.is_staff or (instr and booking.instructor_id == instr.id)):
        raise PermissionError("Not your booking.")


    # --- Delegates: unique by (name + DOB) for the whole booking ---
    delegates = _unique_delegates_for_booking(booking)


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

def _get_or_create_invoice(booking):
    inv = getattr(booking, "invoice", None)
    if inv:
        return inv
    return Invoice.objects.create(
        booking=booking,
        instructor=booking.instructor,
        invoice_date=now().date(),
        account_name=getattr(booking.instructor, "name_on_account", "") or "",
        sort_code=getattr(booking.instructor, "bank_sort_code", "") or "",
        account_number=getattr(booking.instructor, "bank_account_number", "") or "",
    )


@login_required
def instructor_booking_detail(request, pk):
    """Instructor booking detail with tabs (registers, assessments, feedback, closure, invoicing).
    On close, automatically email PDFs to admin (DEV -> DEV_CATCH_ALL_EMAIL)."""
    instr = getattr(request.user, "instructor", None)
    booking = get_object_or_404(
        Booking.objects.select_related("course_type", "business", "instructor", "training_location"),
        pk=pk,
    )
    if not instr or booking.instructor_id != instr.id:
        messages.error(request, "You do not have access to this booking.")
        return redirect("instructor_bookings")

    is_locked = (getattr(booking, "status", "") == "completed")

    
    if request.method == "POST":
        action = request.POST.get("action")

        # ---- NEW: Save/Send invoice from Invoicing tab ----
        if action in ("save_draft", "send_admin"):
            inv = _get_or_create_invoice(booking)

            # Update invoice header fields
            inv.instructor_ref = request.POST.get("instructor_ref", "") or ""
            inv_date_str = request.POST.get("invoice_date") or ""
            try:
                from datetime import datetime
                inv.invoice_date = datetime.strptime(inv_date_str, "%Y-%m-%d").date()
            except Exception:
                from django.utils.timezone import now
                inv.invoice_date = now().date()

            inv.account_name   = request.POST.get("account_name", "") or ""
            inv.sort_code      = request.POST.get("sort_code", "") or ""
            inv.account_number = request.POST.get("account_number", "") or ""
            inv.status = "draft"
            inv.save()

            # Base instructor fee editable -> stored on Booking
            base_amount = request.POST.get("base_amount")
            if base_amount is not None and base_amount != "":
                try:
                    from decimal import Decimal
                    booking.instructor_fee = Decimal(str(base_amount))
                    booking.save(update_fields=["instructor_fee"])
                except Exception:
                    pass

            # Replace additional items
            try:
                descs = request.POST.getlist("item_desc")
                amts  = request.POST.getlist("item_amount")
            except Exception:
                descs, amts = [], []
            inv.items.all().delete()
            from decimal import Decimal
            for d, a in zip(descs, amts):
                d = (d or "").strip()
                if not d and (a is None or a == ""):
                    continue
                try:
                    amt = Decimal(str(a or 0))
                except Exception:
                    amt = Decimal("0")
                inv.items.create(description=d or "", amount=amt)

            if action == "send_admin":
                # Render the same PDF the preview uses
                resp = invoice_preview(request, pk=booking.pk)

                # Extract bytes from HttpResponse (works for normal or streaming responses)
                try:
                    pdf_bytes = bytes(resp.content)
                except Exception:
                    try:
                        pdf_bytes = b"".join(resp.streaming_content)
                    except Exception:
                        pdf_bytes = b""

                if not pdf_bytes:
                    messages.error(request, "Failed to generate invoice PDF.")
                    return redirect("instructor_booking_detail", pk=booking.pk)

                # Figure out recipient (same logic you used elsewhere)
                to_addr = (getattr(settings, "DEV_CATCH_ALL_EMAIL", None) if settings.DEBUG else
                        (getattr(settings, "ADMIN_EMAIL", None) or getattr(settings, "ADMIN_INBOX_EMAIL", None)))
                if not to_addr:
                    messages.error(request, "No admin email configured; could not send invoice.")
                    return redirect("instructor_booking_detail", pk=booking.pk)

                # Email it
                subj = f"Invoice – {booking.course_type.name} ({booking.course_reference or booking.pk})"
                body = (
                    "Hi,\n\n"
                    "Please find attached the instructor invoice for this course.\n\n"
                    f"Course: {booking.course_type.name}\n"
                    f"Reference: {booking.course_reference or booking.pk}\n"
                    f"Instructor: {booking.instructor.name}\n\n"
                    "Regards,\nUnicorn Training System"
                )
                email = EmailMessage(
                    subject=subj,
                    body=body,
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                    to=[to_addr],
                )
                filename = f"invoice-{booking.course_reference or booking.pk}.pdf"
                email.attach(filename, pdf_bytes, "application/pdf")
                email.send(fail_silently=False)

                inv.status = "sent"  # or "awaiting_review" if you prefer
                inv.save(update_fields=["status"])

                messages.success(request, "Invoice emailed to admin.")
                return redirect("instructor_booking_detail", pk=booking.pk)



        if action == "close_course":

            reg_manual    = request.POST.get("reg_manual") == "1"
            assess_manual = request.POST.get("assess_manual") == "1"
            booking.status = "completed"
            fields = ["status"]
            if hasattr(booking, "closure_register_manual"):
                booking.closure_register_manual = reg_manual;  fields.append("closure_register_manual")
            if hasattr(booking, "closure_assess_manual"):
                booking.closure_assess_manual = assess_manual; fields.append("closure_assess_manual")
            booking.save(update_fields=fields)

            # ---- assemble PDFs and email ----
            def _resp_bytes(resp):
                try:
                    if hasattr(resp, "content"):
                        return bytes(resp.content)
                    if hasattr(resp, "streaming_content"):
                        return b"".join(resp.streaming_content)
                except Exception:
                    return b""
                return b""

            attachments = []
            notes = []

            # Registers PDFs (per day)
            try:
                for d in BookingDay.objects.filter(booking=booking).order_by("date"):
                    r = instructor_day_registers_pdf(request, pk=d.id)
                    b = _resp_bytes(r)
                    if b:
                        attachments.append((f"registers_{d.date:%Y%m%d}.pdf", b, "application/pdf"))
            except Exception as e:
                notes.append(f"Registers: {e}")

            # Feedback PDF
            try:
                r = instructor_feedback_pdf_all(request, booking.id)
                b = _resp_bytes(r)
                if b:
                    attachments.append(("feedback_all.pdf", b, "application/pdf"))
            except Exception as e:
                notes.append(f"Feedback: {e}")

            # Assessment matrix PDF (best-effort)
            try:
                r = instructor_assessment_pdf(request, booking.id)
                b = _resp_bytes(r)
                if b:
                    attachments.append(("assessments.pdf", b, "application/pdf"))
            except Exception as e:
                notes.append(f"Assessments: {e}")

            try:
                to_addr = getattr(settings, "DEV_CATCH_ALL_EMAIL", None) if settings.DEBUG else (
                    getattr(settings, "ADMIN_EMAIL", None) or getattr(settings, "ADMIN_INBOX_EMAIL", None)
                ) or "info@unicornsafety.co.uk"

                subject = f"Course documents – {booking.course_type.name} ({booking.course_reference or booking.pk})"
                body = (
                    "Hi,\n\nAttached are the course documents for the booking that has just been closed.\n\n"
                    f"Course: {booking.course_type.name}\n"
                    f"Reference: {booking.course_reference or booking.pk}\n"
                    f"Location: {getattr(booking.training_location, 'name', '')}\n"
                    f"Instructor: {booking.instructor.name}\n\n"
                    "Regards,\nUnicorn Training System"
                )
                email = EmailMessage(subject, body, getattr(settings, "DEFAULT_FROM_EMAIL", None), [to_addr])
                for fname, data, ctype in attachments:
                    email.attach(fname, data, ctype)
                email.send(fail_silently=False)
                if notes:
                    messages.warning(request, "Course closed and emailed, with notes: " + "; ".join(notes))
                else:
                    messages.success(request, "Course closed and documents emailed to admin.")
            except Exception as e:
                messages.warning(request, f"Course closed but email failed: {e}")

            return redirect("instructor_booking_detail", pk=booking.pk)

        if not is_locked:
            notes_form = BookingNotesForm(request.POST, instance=booking)
            if notes_form.is_valid():
                notes_form.save()
                messages.success(request, "Course notes saved.")
                return redirect("instructor_booking_detail", pk=booking.pk)
        else:
            notes_form = BookingNotesForm(instance=booking)
    else:
        notes_form = BookingNotesForm(instance=booking)

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

    day_counts = list(days_qs.values_list("n", flat=True))
    registers_all_days = bool(day_counts) and all((n or 0) > 0 for n in day_counts)

    delegate_outcomes = list(DelegateRegister.objects.filter(booking_day__booking=booking).values_list("outcome", flat=True))
    completed_outcomes = {"pass", "fail", "dnf"}
    has_any = bool(delegate_outcomes)
    assessments_all_complete = has_any and all(((o or "").lower() in completed_outcomes) for o in delegate_outcomes)

    booking_dates = list(days_qs.values_list("date", flat=True))
    if booking_dates:
        fb_qs = (FeedbackResponse.objects.filter(course_type_id=booking.course_type_id, date__in=booking_dates, instructor_id=booking.instructor_id).order_by("-date", "-created_at"))
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
        "fb_qs": fb_qs,
        "fb_count": fb_count,
        "fb_avg": fb_avg,
        "registers_all_days": registers_all_days,
        "assessments_all_complete": assessments_all_complete,
        "is_locked": is_locked,
        "registers_manual": getattr(booking, "closure_register_manual", False),
        "assessments_manual": getattr(booking, "closure_assess_manual", False),
    }

    try:
        ctx.update(_invoicing_tab_context(booking))
    except Exception:
        pass

    try:
        ctx.update(_assessment_context(booking, request.user))
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
    PDF: Delegate register (A4 landscape).
    Main row: Full name | Date of birth | Job title | Emp. ID | Health declaration
    If a delegate has notes, a second sub-row is drawn immediately underneath:
        [ Notes ] | <wrapped notes spanning remaining width>
    """
    # Lazy imports
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors

    from .models import BookingDay, DelegateRegister

    # --- Fetch data ---
    day = get_object_or_404(
        BookingDay.objects.select_related(
            "booking",
            "booking__course_type",
            "booking__business",
            "booking__training_location",
            "booking__instructor",
        ),
        pk=pk,
    )
    booking = day.booking
    regs = list(DelegateRegister.objects.filter(booking_day=day).order_by("name", "id"))

    # --- Page geometry ---
    page_w, page_h = landscape(A4)
    left, right = 12 * mm, page_w - 12 * mm
    top, bottom = page_h - 12 * mm, 12 * mm

    # Main table columns (no dedicated notes column)
    col_name   = 62 * mm
    col_dob    = 24 * mm
    col_job    = 46 * mm
    col_emp    = 22 * mm
    col_health = (right - left) - (col_name + col_dob + col_job + col_emp)

    # Notes sub-row widths
    notes_label_w   = 20 * mm
    notes_content_w = (right - left) - notes_label_w

    # Sizing
    row_min_h  = 12 * mm
    line_gap   = 4
    pad_x      = 2 * mm
    pad_y      = 3
    header_pad = 6 * mm  # extra padding below header line before table

    # (Adjust these to match your matrix/assessment PDFs as needed)
    FOOTER_LINE_1 = "Unicorn Training — Delegate Register"
    FOOTER_LINE_2 = "This form may contain personal data. Handle and store appropriately."

    # --- Wrapping helpers ---
    def wrap_lines(c, text, font, size, max_w):
        if not text:
            return []
        words = text.split()
        if not words:
            return []
        lines, cur = [], words[0]
        for w in words[1:]:
            t = f"{cur} {w}"
            if c.stringWidth(t, font, size) <= max_w:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def cell_height(c, text, font="Helvetica", size=9, max_w=1000, min_h=row_min_h):
        lines = wrap_lines(c, text or "", font, size, max_w)
        return max(min_h, (len(lines) * (size + line_gap)) + pad_y * 2) if lines else min_h

    # --- Header/footer ---
    def draw_header_block(c):
        """
        Draws the header and returns the y position of the horizontal line
        under the header. The table should start below that line.
        """
        c.saveState()
        try:
            y = top
            c.setFont("Helvetica-Bold", 14)
            c.drawString(left, y, "Delegate Register")
            c.setFont("Helvetica", 9)

            y -= 7 * mm
            if booking and booking.course_type:
                c.drawString(left, y, f"Course: {booking.course_type.name}")
                y -= 5 * mm

            c.drawString(left, y, f"Date: {day.date.strftime('%d %b %Y')}")
            y -= 5 * mm

            if booking and booking.instructor:
                c.drawString(left, y, f"Instructor: {booking.instructor.name}")
                y -= 5 * mm

            if booking and booking.training_location:
                loc = booking.training_location
                addr = ", ".join(filter(None, [loc.name, loc.address_line, loc.town, loc.postcode]))
                c.drawString(left, y, f"Location: {addr}")
                y -= 5 * mm

            if booking and booking.course_reference:
                c.drawString(left, y, f"Reference: {booking.course_reference}")
                y -= 5 * mm

            c.setStrokeColor(colors.lightgrey)
            c.line(left, y, right, y)
            return y
        finally:
            c.restoreState()

    def draw_footer(c):
        """
        Draw a two-line footer and page number.
        Draw this *after* finishing page content and *before* showPage().
        """
        c.saveState()
        try:
            # fine line above footer
            c.setStrokeColor(colors.lightgrey)
            c.line(left, bottom + 12, right, bottom + 12)

            c.setFont("Helvetica", 8)
            c.setFillGray(0.35)
            c.drawString(left, bottom + 5 * mm, FOOTER_LINE_1)
            c.drawString(left, bottom + 3 * mm, FOOTER_LINE_2)
            c.drawRightString(right, bottom + 3 * mm, f"Page {c.getPageNumber()}")
            c.setFillGray(0)
            c.setStrokeColor(colors.black)
        finally:
            c.restoreState()

    def draw_header_row(c, y):
        c.saveState()
        try:
            c.setFont("Helvetica-Bold", 9)
            x = left
            headers = [
                ("Full name", col_name),
                ("Date of birth", col_dob),
                ("Job title", col_job),
                ("Emp. ID", col_emp),
                ("Health declaration", col_health),
            ]
            for title, w in headers:
                c.rect(x, y - row_min_h, w, row_min_h, stroke=1, fill=0)
                c.drawString(x + pad_x, y - row_min_h + pad_y, title)
                x += w
        finally:
            c.restoreState()

    # --- Draw one delegate (with optional notes sub-row) ---
    def draw_one_row(c, r, y_top):
        """
        Returns new y (next row top) or None if a page break is needed.
        """
        name  = (getattr(r, "name", "") or "").strip()
        dob   = r.date_of_birth.strftime("%d/%m/%Y") if getattr(r, "date_of_birth", None) else ""
        job   = (getattr(r, "job_title", "") or "").strip()
        emp   = (getattr(r, "employee_id", "") or "").strip()
        notes = (getattr(r, "notes", "") or "").strip()

        c.setFont("Helvetica", 9)
        h_name = cell_height(c, name, max_w=col_name - 2 * pad_x)
        h_job  = cell_height(c, job,  max_w=col_job  - 2 * pad_x)
        base_h = max(row_min_h, h_name, h_job)

        notes_h = cell_height(c, notes, max_w=notes_content_w - 2 * pad_x, min_h=10 * mm) if notes else 0
        total_h = base_h + notes_h

        # Keep a buffer above the footer
        if y_top - total_h < (bottom + 24 * mm):
            return None

        # --- base row ---
        x = left

        # Name
        c.rect(x, y_top - base_h, col_name, base_h, stroke=1, fill=0)
        lines = wrap_lines(c, name, "Helvetica", 9, col_name - 2 * pad_x) or [""]
        yy = y_top - pad_y - 9
        for ln in lines:
            c.drawString(x + pad_x, yy, ln)
            yy -= (9 + line_gap)
            if yy < y_top - base_h + pad_y:
                break
        x += col_name

        # DOB
        c.rect(x, y_top - base_h, col_dob, base_h, stroke=1, fill=0)
        if dob:
            c.drawString(x + pad_x, y_top - base_h + pad_y, dob)
        x += col_dob

        # Job
        c.rect(x, y_top - base_h, col_job, base_h, stroke=1, fill=0)
        lines = wrap_lines(c, job, "Helvetica", 9, col_job - 2 * pad_x)
        if lines:
            yy = y_top - pad_y - 9
            for ln in lines:
                c.drawString(x + pad_x, yy, ln)
                yy -= (9 + line_gap)
                if yy < y_top - base_h + pad_y:
                    break
        x += col_job

        # Emp ID
        c.rect(x, y_top - base_h, col_emp, base_h, stroke=1, fill=0)
        c.drawString(x + pad_x, y_top - base_h + pad_y, emp or "—")
        x += col_emp

        # Health declaration: show stored value if present, otherwise a faint signature line
        c.rect(x, y_top - base_h, col_health, base_h, stroke=1, fill=0)
        if hasattr(r, "get_health_status_display"):
            health_txt = (r.get_health_status_display() or "").strip()
        else:
            health_txt = (getattr(r, "health_status", "") or "").strip()

        if health_txt:
            lines = wrap_lines(c, health_txt, "Helvetica", 9, col_health - 2 * pad_x)
            yy = y_top - pad_y - 9
            for ln in lines:
                c.drawString(x + pad_x, yy, ln)
                yy -= (9 + line_gap)
                if yy < y_top - base_h + pad_y:
                    break
        else:
            sig_y = y_top - base_h + base_h / 2
            c.setStrokeColor(colors.lightgrey)
            c.line(x + pad_x, sig_y, x + col_health - pad_x, sig_y)
            c.setStrokeColor(colors.black)

        y = y_top - base_h

        # --- optional notes sub-row ---
        if notes:
            # label
            c.rect(left, y - notes_h, notes_label_w, notes_h, stroke=1, fill=0)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(left + pad_x, y - notes_h + pad_y, "Notes")
            c.setFont("Helvetica", 9)

            # content
            nx = left + notes_label_w
            c.rect(nx, y - notes_h, notes_content_w, notes_h, stroke=1, fill=0)
            lines = wrap_lines(c, notes, "Helvetica", 9, notes_content_w - 2 * pad_x)
            if lines:
                yy = y - pad_y - 9
                for ln in lines:
                    c.drawString(nx + pad_x, yy, ln)
                    yy -= (9 + line_gap)
                    if yy < y - notes_h + pad_y:
                        break
            y -= notes_h

        return y

    # --- Build PDF (force download) ---
    filename = f"register-{day.pk}.pdf"
    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'  # << force download

    c = canvas.Canvas(resp, pagesize=landscape(A4))
    c.setTitle(f"Delegate Register — {booking.course_reference if booking else day.pk}")

    def start_new_page():
        header_line_y = draw_header_block(c)
        y0 = header_line_y - header_pad
        draw_header_row(c, y0)
        return y0 - row_min_h - 2

    y = start_new_page()

    if not regs:
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(left, y - 8 * mm, "No delegates recorded.")
        # footer + page
        draw_footer(c)
        c.showPage()
        c.save()
        return resp

    for r in regs:
        new_y = draw_one_row(c, r, y)
        if new_y is None:
            # finish this page
            draw_footer(c)
            c.showPage()
            y = start_new_page()
            new_y = draw_one_row(c, r, y) or (y - (row_min_h * 2))
        y = new_y - 1  # small gap

    # finish last page
    draw_footer(c)
    c.showPage()
    c.save()
    return resp


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
    # Deduplicate delegates by (name + DOB)
    delegates = _unique_delegates_for_booking(booking)

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
    # Unique delegates (one per person across the booking)
    delegates = _unique_delegates_for_booking(booking)

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

@login_required
def invoice_preview(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related("course_type","business","instructor","training_location"),
        pk=pk,
    )
    instr = getattr(request.user, "instructor", None)
    if not instr or instr.id != booking.instructor_id:
        return HttpResponseForbidden("Not allowed.")

    # ---- Build context for the HTML invoice template ----
    inv = getattr(booking, "invoice", None) or Invoice.objects.create(
        booking=booking, instructor=booking.instructor, invoice_date=now().date()
    )

    addr_parts = [
        getattr(booking.instructor, "address_line", ""),
        getattr(booking.instructor, "town", ""),
        getattr(booking.instructor, "postcode", ""),
    ]
    from_address = "\n".join([p for p in addr_parts if p.strip()])

    base_fee = Decimal(str(booking.instructor_fee or 0))
    items = [{"description": f"{booking.course_type.name} – {booking.business.name} – {booking.course_date:%d/%m/%Y}",
              "amount": f"{base_fee:.2f}"}]
    for it in inv.items.all().order_by("id"):
        items.append({"description": it.description or "", "amount": f"{(it.amount or 0):.2f}"})

    ctx = {
        "instructor_name": booking.instructor.name if booking.instructor else "",
        "from_address": from_address,
        "invoice_date": (inv.invoice_date or now().date()).strftime("%d/%m/%Y"),
        "course_ref": booking.course_reference or "",
        "instructor_ref": inv.instructor_ref or "",
        "items": items,
        "invoice_total": f"{(base_fee + sum((x.amount or 0) for x in inv.items.all())):.2f}",
        "account_name":   inv.account_name   or getattr(booking.instructor, "name_on_account", "") or "",
        "sort_code":      inv.sort_code      or getattr(booking.instructor, "bank_sort_code", "") or "",
        "account_number": inv.account_number or getattr(booking.instructor, "bank_account_number", "") or "",
    }

    html = render_to_string("invoicing/invoice.html", ctx)  # your HTML template

    # ---- Run wkhtmltopdf ----
    wk = getattr(settings, "WKHTMLTOPDF_CMD", None)
    if not wk or not os.path.exists(wk):
        return HttpResponseServerError("wkhtmltopdf not configured.")

    # Use a temp HTML file so asset paths resolve correctly
    with tempfile.TemporaryDirectory() as tmp:
        html_path = os.path.join(tmp, "invoice.html")
        pdf_path  = os.path.join(tmp, "invoice.pdf")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        # Common flags: quiet, enable-local-file-access for Windows
        cmd = [wk, "--quiet", "--enable-local-file-access", html_path, pdf_path]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0 or not os.path.exists(pdf_path):
            # Surface wkhtmltopdf errors to help debugging
            return HttpResponseServerError(
                "wkhtmltopdf failed:\n" + (proc.stderr.decode("utf-8", errors="ignore") or "Unknown error")
            )

        with open(pdf_path, "rb") as f:
            pdf = f.read()

    response = HttpResponse(pdf, content_type="application/pdf")
    filename = f"invoice-{booking.course_reference or booking.pk}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


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

@login_required
def send_course_docs(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related("course_type", "business", "instructor", "training_location"),
        pk=pk,
    )
    instr = getattr(request.user, "instructor", None)
    if not instr or instr.id != booking.instructor_id:
        messages.error(request, "You do not have access to this booking.")
        return redirect("instructor_bookings")

    if request.method != "POST":
        return redirect("instructor_booking_detail", pk=booking.pk)

    n = email_all_course_docs_to_admin(booking)
    if n:
        messages.success(request, f"Sent {n} PDF document(s) to admin.")
    else:
        messages.warning(request, "No documents were generated to send.")
    return redirect("instructor_booking_detail", pk=booking.pk)




@login_required
@user_passes_test(lambda u: u.is_superuser)
def email_diagnostics(request):
    """
    TEMP endpoint to debug SMTP on Render. Plain-text output.
    Only accessible to logged-in superusers.
    """
    mask = lambda s: (s[:3] + "…" + s[-3:]) if s else ""
    lines = []
    lines.append("== EMAIL SETTINGS SEEN BY DJANGO ==")
    lines.append(f"EMAIL_BACKEND        = {settings.EMAIL_BACKEND}")
    lines.append(f"EMAIL_HOST           = {getattr(settings, 'EMAIL_HOST', '')}")
    lines.append(f"EMAIL_PORT           = {getattr(settings, 'EMAIL_PORT', '')}")
    lines.append(f"EMAIL_USE_TLS        = {getattr(settings, 'EMAIL_USE_TLS', '')}")
    lines.append(f"EMAIL_HOST_USER      = {getattr(settings, 'EMAIL_HOST_USER', '')}")
    pw = getattr(settings, 'EMAIL_HOST_PASSWORD', '')
    lines.append(f"EMAIL_HOST_PASSWORD  = {mask(pw)}")
    lines.append(f"DEFAULT_FROM_EMAIL   = {getattr(settings, 'DEFAULT_FROM_EMAIL', '')}")
    lines.append(f"ADMIN_INBOX_EMAIL    = {getattr(settings, 'ADMIN_INBOX_EMAIL', '')}")
    lines.append(f"DEV_CATCH_ALL_EMAIL  = {getattr(settings, 'DEV_CATCH_ALL_EMAIL', '')}")
    lines.append("")

    # Try a real SMTP handshake
    lines.append("== SMTP HANDSHAKE ==")
    host = getattr(settings, 'EMAIL_HOST', 'smtp.gmail.com')
    port = int(getattr(settings, 'EMAIL_PORT', 587) or 587)
    user = getattr(settings, 'EMAIL_HOST_USER', '')
    pwd  = getattr(settings, 'EMAIL_HOST_PASSWORD', '')

    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            s = smtplib.SMTP(host, port, timeout=30)
            s.set_debuglevel(1)  # print SMTP conversation
            s.ehlo()
            if getattr(settings, 'EMAIL_USE_TLS', True):
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
            if user:
                s.login(user, pwd)
            s.quit()
        lines.append("SMTP handshake: OK")
        lines.append("")
        lines.append("Raw SMTP dialogue:")
        lines.append(buf.getvalue())
    except Exception as e:
        lines.append(f"SMTP handshake: FAILED -> {type(e).__name__}: {e}")

    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")

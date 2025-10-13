import json
from datetime import timedelta, datetime, time as dtime

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q, Count, Min
from django.db.models.deletion import ProtectedError
from django.forms import modelformset_factory, inlineformset_factory
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.http import require_http_methods

from .models import (
    Business, CourseType, Instructor, Booking, TrainingLocation,
    StaffProfile, BookingDay, DelegateRegister, CourseCompetency
)
from .forms import (
    BusinessForm, CourseTypeForm, TrainingLocationForm,
    InstructorForm, BookingForm, DelegateRegisterAdminForm,CourseCompetencyForm
)

# =========================
# Helpers / guards
# =========================
def is_admin(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.groups.filter(name__iexact="admin").exists()
    )

def admin_required(view_func):
    @login_required
    def _wrapped(request, *args, **kwargs):
        if is_admin(request.user):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied
    return _wrapped

def _ensure_core_groups():
    for gname in ("admin", "instructor"):
        Group.objects.get_or_create(name=gname)

def _make_local_aware(local_date, local_time):
    """
    Combine date + time into an aware datetime in the current TIME_ZONE,
    handling DST transitions (ambiguous/non-existent times) gracefully.
    """
    tz = timezone.get_current_timezone()
    t = local_time or dtime(0, 0)
    naive = datetime.combine(local_date, t)

    try:
        return timezone.make_aware(naive, tz)
    except Exception:
        # Try resolving ambiguity (autumn clock change)
        try:
            return timezone.make_aware(naive.replace(fold=1), tz)
        except Exception:
            # Non-existent local times (spring forward): nudge +1h
            return timezone.make_aware(naive + timedelta(hours=1), tz)

# imports you likely already have; add any missing
from datetime import datetime, time
from django.db.models import Max, Q
from django.utils import timezone

def _auto_update_booking_statuses():
    """
    1) Scheduled -> In progress     when a day starts
    2) Scheduled/In progress -> Awaiting instructor closure when the last day is finished
    """
    now = timezone.localtime()
    today = now.date()
    now_t = now.time()

    # --- 1) SCHEDULED -> IN PROGRESS when today's day has started ---
    Booking.objects.filter(status="scheduled").filter(
        Q(days__date=today, days__start_time__lte=now_t)
    ).update(status="in_progress")

    # --- 2) -> AWAITING_CLOSURE when the final day has ended ---
    # We’ll look at any booking that is still scheduled or in_progress.
    # Annotate with the last day date to minimise queries.
    qs = (
        Booking.objects
        .filter(status__in=["scheduled", "in_progress"])
        .annotate(last_day=Max("days__date"))
    )

    DEFAULT_END = time(17, 0)  # fallback if you don't store an end_time yet

    for b in qs:
        if not b.last_day:
            continue  # no days yet

        # If today is before the last day, we obviously aren't finished
        if today < b.last_day:
            continue

        # work out the closure moment for the last day
        end_t = DEFAULT_END
        # If you have an end_time field on BookingDay, prefer it:
        ld = b.days.filter(date=b.last_day).order_by("-id").first()
        if ld and getattr(ld, "end_time", None):
            end_t = ld.end_time

        # build an aware datetime for the last day’s end moment
        last_dt = timezone.make_aware(datetime.combine(b.last_day, end_t))
        if now >= last_dt:
            # flip to awaiting closure
            if b.status in ("scheduled", "in_progress"):
                b.status = "awaiting_closure"
                b.save(update_fields=["status"])


# =========================
# Admin dashboard
# =========================
@admin_required
def dashboard(request):
    return render(request, "admin/dashboard.html")


# =========================
# Businesses
# =========================
@admin_required
def business_list(request):
    q = (request.GET.get("q") or "").strip()

    qs = Business.objects.all()

    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(town__icontains=q) |
            Q(postcode__icontains=q)
            # If your model has these, uncomment:
            # | Q(primary_contact_name__icontains=q)
            # | Q(primary_contact_email__icontains=q)
            # Or search related contacts (adjust relation name):
            # | Q(contacts__name__icontains=q)
            # | Q(contacts__email__icontains=q)
        ).distinct()

    rows = []
    for b in qs.order_by("name"):
        rows.append({
            "cells": [b.name, b.town or "", b.postcode or ""],
            "edit_url": reverse("admin_business_edit", args=[b.id]),
        })

    ctx = {
        "title": "Businesses",
        "headers": ["Name", "Town", "Postcode"],
        "rows": rows,
        "create_url": reverse("admin_business_new"),
        "q": q,                   # <- keeps the search box filled
        "list_id": "businesses",  # <- tells the template to show the search UI
    }
    return render(request, "admin/list.html", ctx)



@admin_required
def business_form(request, pk=None):
    obj = get_object_or_404(Business, pk=pk) if pk else None

    # --- Save flow ---------------------------------------------------------
    if request.method == "POST":
        form = BusinessForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            messages.success(request, "Changes saved.")
            if "save_return" in request.POST:
                return redirect("admin_business_list")
            return redirect("admin_business_edit", pk=obj.id)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = BusinessForm(instance=obj)

    # --- Locations (left card) --------------------------------------------
    locations = []
    add_location_url = None
    if obj:
        locations = TrainingLocation.objects.filter(business=obj).order_by("name")
        add_location_url = reverse("admin_location_new", args=[obj.id])

    # --- Bookings (right card) + filters ----------------------------------
    bookings = []
    instructors = []
    statuses = []

    # GET filters (won't interfere with the POST save form)
    f_status = request.GET.get("b_status", "all")
    f_instr  = request.GET.get("b_instr") or ""
    f_from   = request.GET.get("b_from") or ""
    f_to     = request.GET.get("b_to") or ""

    if obj:
        base = (
            Booking.objects
            .filter(business=obj)
            .select_related("course_type", "instructor", "training_location")
            .annotate(first_day=Min("days__date"))   # earliest day from related BookingDay rows
        )

        # Distinct statuses present for this business (for tabs)
        statuses = (
            base.order_by()
                .values_list("status", flat=True)
                .distinct()
        )

        # Instructors who have bookings with this business (for dropdown)
        instructors = (
            Instructor.objects
            .filter(bookings__business=obj)   # related_name 'bookings' on Booking.instructor
            .distinct()
            .order_by("name")
        )

        qs = base

        # Status filter
        if f_status and f_status != "all":
            qs = qs.filter(status=f_status)

        # Instructor filter
        if f_instr:
            qs = qs.filter(instructor_id=f_instr)

        # Date range (use course_date if set, otherwise annotated first_day)
        if f_from:
            qs = qs.filter(Q(course_date__gte=f_from) | Q(first_day__gte=f_from))
        if f_to:
            qs = qs.filter(Q(course_date__lte=f_to) | Q(first_day__lte=f_to))

        bookings = (
            qs.order_by("-first_day", "-course_date", "-created_at")
              .distinct()[:100]
        )

    # --- Render ------------------------------------------------------------
    return render(request, "admin/form_business.html", {
        "title": ("Edit Business" if obj else "New Business"),
        "form": form,
        "business": obj,

        # locations card
        "locations": locations,
        "add_location_url": add_location_url,

        # bookings card + filter data
        "bookings": bookings,
        "booking_statuses": statuses,
        "booking_instructors": instructors,
        "b_status": f_status,
        "b_instr": f_instr,
        "b_from": f_from,
        "b_to": f_to,

        # misc
        "back_url": reverse("admin_business_list"),
        "delete_url": reverse("admin_business_delete", args=[obj.id]) if obj else None,
    })


# =========================
# Training Locations
# =========================
@admin_required
def location_new(request, business_id):
    biz = get_object_or_404(Business, pk=business_id)
    other_locations = TrainingLocation.objects.filter(business=biz).order_by("name")

    if request.method == "POST":
        form = TrainingLocationForm(request.POST)
        if form.is_valid():
            loc = form.save(commit=False)
            loc.business = biz
            loc.save()  # duplicates allowed
            messages.success(request, "Location saved.")
            if "save_return" in request.POST:
                return redirect("admin_business_edit", pk=biz.id)
            return redirect("admin_location_edit", pk=loc.id)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = TrainingLocationForm()

    return render(request, "admin/form_location.html", {
        "title": f"Add Location – {biz.name}",
        "form": form,
        "business": biz,
        "other_locations": other_locations,
        "back_url": reverse("admin_business_edit", args=[biz.id]),
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
    })


@admin_required
def location_edit(request, pk):
    loc = get_object_or_404(TrainingLocation, pk=pk)
    biz = loc.business
    other_locations = TrainingLocation.objects.filter(business=biz).exclude(pk=loc.pk).order_by("name")

    if request.method == "POST":
        form = TrainingLocationForm(request.POST, instance=loc)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.business = biz
            obj.save()
            messages.success(request, "Location saved.")
            if "save_return" in request.POST:
                return redirect("admin_business_edit", pk=biz.id)
            return redirect("admin_location_edit", pk=obj.id)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = TrainingLocationForm(instance=loc)

    return render(request, "admin/form_location.html", {
        "title": f"Edit Location – {biz.name}",
        "form": form,
        "business": biz,
        "other_locations": other_locations,
        "back_url": reverse("admin_business_edit", args=[biz.id]),
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
    })

@admin_required
@require_http_methods(["POST"])
def location_delete(request, pk):
    loc = get_object_or_404(TrainingLocation, pk=pk)  # <-- TrainingLocation
    # keep the parent to return to its edit page after delete
    business_pk = getattr(loc, "business_id", None)
    name = loc.name

    try:
        loc.delete()
    except ProtectedError:
        messages.error(
            request,
            f'“{name}” can’t be deleted because it has related records.'
        )
        if business_pk:
            return redirect("admin_business_edit", pk=business_pk)
        return redirect("admin_business_list")

    messages.success(request, f'Location “{name}” deleted.')
    if business_pk:
        return redirect("admin_business_edit", pk=business_pk)
    return redirect("admin_business_list")

# =========================
# Course Types
# =========================
@admin_required
def course_list(request):
    rows = []
    for c in CourseType.objects.order_by("name"):
        rows.append({
            "cells": [c.name, c.code, c.duration_days],
            "edit_url": reverse("admin_course_edit", args=[c.id]),
        })
    ctx = {
        "title": "Course Types",
        "headers": ["Name", "Code", "Duration (days)"],
        "rows": rows,
        "create_url": reverse("admin_course_new"),
    }
    return render(request, "admin/list.html", ctx)


CourseCompetencyFormSet = inlineformset_factory(
    parent_model=CourseType,
    model=CourseCompetency,
    form=CourseCompetencyForm,
    fields=["name", "sort_order"],
    extra=0,           # <-- No automatic blank row
    can_delete=True,
)

@admin_required
def course_form(request, pk=None):
    if pk:
        ct = get_object_or_404(CourseType, pk=pk)
        title = "Edit course type"
    else:
        ct = CourseType()
        title = "New course type"

    if request.method == "POST":
        form = CourseTypeForm(request.POST, instance=ct)
        formset = CourseCompetencyFormSet(request.POST, instance=ct, prefix="comps")
        if form.is_valid() and formset.is_valid():
            ct = form.save()
            formset.instance = ct
            formset.save()

            # ✅ Add ONE success message only
            messages.success(request, "Course type saved.")

            # ✅ Branch by which button was pressed
            if "save_return" in request.POST:
                return redirect("admin_course_list")
            return redirect("admin_course_edit", pk=ct.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CourseTypeForm(instance=ct)
        formset = CourseCompetencyFormSet(instance=ct, prefix="comps")

    return render(request, "admin/course_form.html", {
        "title": title,
        "form": form,
        "formset": formset,
    })



@admin_required
@require_http_methods(["GET", "POST"])
def course_delete(request, pk):
    obj = get_object_or_404(CourseType, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Course type deleted.")
        return redirect("admin_course_list")
    return render(request, "admin/confirm_delete.html", {
        "title": "Delete course type",
        "object": obj,
        "back_url": reverse("admin_course_edit", args=[obj.id]),
    })


# =========================
# Bookings — LIST (filters + sort + pagination)
# =========================
@admin_required
def booking_list(request):
    _auto_update_booking_statuses()

    """
    Bookings index with search + filters + sorting + pagination (25/page).
    Columns: Date, Course, Business, Status, Instructor, Ref
    Sort keys: date | course | business | status | instructor | ref
    """
    qs = (Booking.objects
          .select_related("business", "training_location", "course_type", "instructor")
          .all())

    # ----- filters
    q           = (request.GET.get("q") or "").strip()
    status      = (request.GET.get("status") or "").strip()
    business_id = (request.GET.get("business") or "").strip()
    course_id   = (request.GET.get("course_type") or "").strip()
    inst_id     = (request.GET.get("instructor") or "").strip()
    date_from   = (request.GET.get("date_from") or "").strip()
    date_to     = (request.GET.get("date_to") or "").strip()

    if q:
        qs = qs.filter(
            Q(course_reference__icontains=q) |
            Q(business__name__icontains=q)   |
            Q(course_type__name__icontains=q)|
            Q(training_location__name__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    if business_id:
        qs = qs.filter(business_id=business_id)
    if course_id:
        qs = qs.filter(course_type_id=course_id)
    if inst_id:
        qs = qs.filter(instructor_id=inst_id)
    if date_from:
        qs = qs.filter(course_date__gte=date_from)
    if date_to:
        qs = qs.filter(course_date__lte=date_to)

    # ----- sorting
    sort_key = (request.GET.get("o") or "date").strip()
    sort_dir = (request.GET.get("dir") or "desc").strip()  # asc|desc
    allowed = {
        "date":       "course_date",
        "course":     "course_type__name",
        "business":   "business__name",
        "status":     "status",
        "instructor": "instructor__name",
        "ref":        "course_reference",
    }
    order_field = allowed.get(sort_key, "course_date")
    if sort_dir == "desc":
        order_field = "-" + order_field
    qs = qs.order_by(order_field)

    # ----- pagination (25/page)
    paginator  = Paginator(qs, 25)
    page_param = request.GET.get("page")
    page_obj   = paginator.get_page(page_param)

    # ----- status pill styles
    status_style = {
        "scheduled":        {"cls": "badge bg-info text-dark"},
        "cancelled":        {"cls": "badge bg-warning text-dark"},
        "completed":        {"cls": "badge bg-success"},
        "in_progress":      {"cls": "badge bg-dark"},
        "awaiting_closure": {"cls": "badge", "style": "background-color:#6f42c1;color:#fff"},  # purple
    }

    # ----- rows for the table
    rows = []
    for b in page_obj.object_list:
        st = (b.status or "")
        pill = status_style.get(st, {"cls": "badge bg-secondary"})
        label_fn = getattr(b, "get_status_display", lambda: st.replace("_", " ").title())
        rows.append({
            "date":       b.course_date,
            "course":     (b.course_type.name if b.course_type else ""),
            "business":   (b.business.name if b.business else ""),
            "status":     {"label": label_fn(),
                           "cls": pill.get("cls","badge bg-secondary"),
                           "style": pill.get("style","")},
            "instructor": (b.instructor.name if b.instructor else ""),
            "ref":        (b.course_reference or ""),
            "edit_url":   reverse("admin_booking_edit", args=[b.id]),
        })

    # ----- helper to build URLs preserving current filters
    def url_with(**overrides):
        params = {
            "q": q, "status": status, "business": business_id, "course_type": course_id,
            "instructor": inst_id, "date_from": date_from, "date_to": date_to,
            "o": sort_key, "dir": sort_dir, "page": page_obj.number if page_obj.number else 1,
        }
        params.update(overrides)
        # drop page when changing sort to avoid empty pages
        if "o" in overrides or "dir" in overrides:
            params.pop("page", None)
        from urllib.parse import urlencode
        return f"{reverse('admin_booking_list')}?{urlencode({k: v for k, v in params.items() if v})}"

    # ----- build sort header links
    headers = []
    for key, title in [
        ("date","Date"), ("course","Course"), ("business","Business"),
        ("status","Status"), ("instructor","Instructor"), ("ref","Ref")
    ]:
        active = (sort_key == key)
        next_dir = "asc" if (active and sort_dir == "desc") else "desc"
        headers.append({
            "title": title,
            "url": url_with(o=key, dir=next_dir),
            "active": active,
            "dir": sort_dir if active else "",
        })

    # ----- pagination links (no custom template tags needed)
    prev_url = url_with(page=page_obj.previous_page_number()) if page_obj.has_previous() else None
    next_url = url_with(page=page_obj.next_page_number()) if page_obj.has_next() else None
    page_info = f"Page {page_obj.number} of {page_obj.paginator.num_pages}" if page_obj.paginator.num_pages > 1 else ""

    ctx = {
        "title": "Bookings",
        "headers": headers,
        "rows": rows,
        "create_url": reverse("admin_booking_new"),

        "filter_initial": {
            "q": q, "status": status, "business": business_id, "course_type": course_id,
            "instructor": inst_id, "date_from": date_from, "date_to": date_to
        },
        "status_choices": [
            ("", "All statuses"),
            ("scheduled", "Scheduled"),
            ("in_progress", "In progress"),
            ("awaiting_closure", "Awaiting instructor closure"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
        ],
        "businesses":  Business.objects.order_by("name"),
        "course_types": CourseType.objects.order_by("name"),
        "instructors": Instructor.objects.order_by("name"),

        "page_obj": page_obj,
        "page_prev_url": prev_url,
        "page_next_url": next_url,
        "page_info": page_info,

        "sort_key": sort_key,
        "sort_dir": sort_dir,
    }
    return render(request, "admin/bookings_list.html", ctx)


# =========================
# Bookings — FORM (create/edit + per-day rows)
# =========================
@admin_required
@transaction.atomic
def booking_form(request, pk=None):
    """
    Create/edit a booking.
    - On POST: save and replace BookingDay rows from hidden JSON ('booking_days' or 'days_json').
    - On GET: send booking_days_initial_json so the days table repopulates.
    - Additionally passes 'day_rows' (days + delegate counts) for Registers buttons (if used elsewhere).
    """
    obj = get_object_or_404(Booking, pk=pk) if pk else None

    if request.method == "POST":
        form = BookingForm(request.POST, instance=obj)
        if form.is_valid():
            was_new = obj is None
            booking = form.save()

            # ---- helpers ----
            def _parse_time_or_none(s: str | None):
                if not s:
                    return None
                try:
                    hh, mm = s.split(":", 1)
                    return time(int(hh), int(mm))
                except Exception:
                    return None

            # Accept either key name (template writes to both)
            raw_days = request.POST.get("booking_days") or request.POST.get("days_json") or "[]"
            try:
                days_payload = json.loads(raw_days)
                if not isinstance(days_payload, list):
                    days_payload = []
            except json.JSONDecodeError:
                days_payload = []

            if days_payload:
                # Replace all BookingDay rows with what came from the inline table
                booking.days.all().delete()

                for row in days_payload:
                    day_date_str = (row.get("day_date") or "").strip()
                    if not day_date_str:
                        continue

                    # required pieces we know exist in the model
                    dt = datetime.fromisoformat(day_date_str).date()
                    st = _parse_time_or_none(row.get("start_time")) or booking.start_time

                    # optional pieces — uncomment these two lines if your BookingDay has these fields
                    # et = _parse_time_or_none(row.get("end_time"))
                    # note = (row.get("note") or "").strip() or None

                    BookingDay.objects.create(
                        booking=booking,
                        date=dt,
                        start_time=st,
                        # end_time=et,
                        # note=note,
                    )
            else:
                # Fallback: create rows from duration if NEW and no JSON was provided
                if was_new and booking.course_type_id and booking.course_date:
                    # If duration_days can be fractional (e.g. 1.5), we still create whole-day rows here.
                    try:
                        duration_val = booking.course_type.duration_days or 1
                        duration = math.ceil(float(duration_val))
                    except Exception:
                        duration = 1

                    start = booking.course_date
                    for i in range(duration):
                        BookingDay.objects.create(
                            booking=booking,
                            date=start + timedelta(days=i),
                            start_time=booking.start_time,
                        )

            messages.success(request, "Booking saved.")
            if "save_return" in request.POST:
                return redirect("admin_booking_list")
            return redirect("admin_booking_edit", pk=booking.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        # Auto-advance due bookings to "in_progress" before showing the form
        _auto_update_booking_statuses()
        form = BookingForm(instance=obj)

    # ---- maps for client-side behaviour (unchanged) ----
    course_type_map = {
        str(ct.id): {
            "code": ct.code or "",
            "default_course_fee": str(ct.default_course_fee or ""),
            "default_instructor_fee": str(ct.default_instructor_fee or ""),
        }
        for ct in CourseType.objects.order_by("name")
    }

    location_map = {
        str(loc.id): {
            "name": loc.name or "",
            "contact_name": loc.contact_name or "",
            "telephone": loc.telephone or "",
            "email": loc.email or "",
            "address_line": loc.address_line or "",
            "town": loc.town or "",
            "postcode": loc.postcode or "",
            "business_id": str(loc.business_id),
        }
        for loc in TrainingLocation.objects.select_related("business").order_by("name")
    }

    # Seed the inline table (we include start_time; end_time/note left blank unless your model has them)
    if obj and obj.pk:
        booking_days_initial = [
            {
                "day_date": d.date.isoformat(),
                "start_time": d.start_time.strftime("%H:%M") if d.start_time else "",
                "end_time": "",  # uncomment if you add that field and fetch it here
                "note": "",      # uncomment/fill if you add a note field
            }
            for d in obj.days.all().order_by("date")
        ]
    else:
        booking_days_initial = []

    return render(
        request,
        "admin/form_booking.html",
        {
            "title": ("Edit Booking" if obj else "New Booking"),
            "form": form,
            "booking": obj,
            "back_url": reverse("admin_booking_list"),
            "course_type_map_json": json.dumps(course_type_map, cls=DjangoJSONEncoder),
            "location_map_json": json.dumps(location_map, cls=DjangoJSONEncoder),
            "booking_days_initial_json": json.dumps(booking_days_initial, cls=DjangoJSONEncoder),
            "delete_url": reverse("admin_booking_delete", args=[obj.id]) if obj else None,
        },
    )





@admin_required
@require_http_methods(["GET", "POST"])
def booking_delete(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related("business", "course_type", "training_location"),
        pk=pk
    )

    if request.method == "POST":
        ref = booking.course_reference or ""
        booking.delete()
        messages.success(request, f"Booking {ref} deleted.")
        return redirect("admin_booking_list")

    return render(request, "admin/confirm_delete_booking.html", {
        "title": "Delete booking",
        "booking": booking,
        "back_url": reverse("admin_booking_edit", args=[booking.pk]),
        # a handy link to cancel instead of delete
        "cancel_url": reverse("admin_booking_cancel", args=[booking.pk]),
    })



@admin_required
@require_http_methods(["GET", "POST"])
def booking_cancel(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related("business", "course_type", "training_location"),
        pk=pk
    )

    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        booking.status = "cancelled"
        booking.cancel_reason = reason
        booking.cancelled_at = timezone.now()
        booking.save(update_fields=["status", "cancel_reason", "cancelled_at"])
        messages.success(request, "Booking cancelled.")
        return redirect("admin_booking_edit", pk=booking.pk)

    # GET – show confirm cancel
    return render(request, "admin/confirm_cancel.html", {
        "title": "Cancel booking",
        "booking": booking,
        "back_url": reverse("admin_booking_edit", args=[booking.pk]),
    })

# --- Reinstate a cancelled booking ---
@admin_required
@require_http_methods(["GET", "POST"])
def booking_reinstate(request, pk):
    booking = get_object_or_404(
        Booking.objects.select_related("business", "course_type", "training_location"),
        pk=pk
    )

    if request.method == "POST":
        booking.status = "scheduled"
        booking.cancel_reason = ""
        booking.cancelled_at = None
        booking.save(update_fields=["status", "cancel_reason", "cancelled_at"])
        messages.success(request, "Booking reinstated.")
        return redirect("admin_booking_edit", pk=booking.pk)

    return render(request, "admin/confirm_reinstate.html", {
        "title": "Reinstate booking",
        "booking": booking,
        "back_url": reverse("admin_booking_edit", args=[booking.pk]),
    })

# =========================
# Users (admin creates/edits)
# =========================
class AdminUserCreateForm(forms.ModelForm):
    password = forms.CharField(
        label="Initial password",
        widget=forms.PasswordInput,
        required=True,
    )
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Tick one or more roles (e.g., admin, instructor).",
    )
    must_change_password = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Force this user to change their password at next login."
    )

    class Meta:
        model = User
        fields = ["username", "email", "password", "is_active", "groups", "must_change_password"]


class AdminUserEditForm(forms.ModelForm):
    new_password = forms.CharField(
        label="Reset password",
        widget=forms.PasswordInput,
        required=False,
        help_text="Leave blank to keep the current password.",
    )
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Tick one or more roles (e.g., admin, instructor).",
    )
    must_change_password = forms.BooleanField(
        required=False,
        initial=False,
        help_text="If ticked, user will be forced to change password next login."
    )

    class Meta:
        model = User
        fields = ["username", "email", "is_active", "groups", "must_change_password"]


@admin_required
def admin_user_list(request):
    _ensure_core_groups()
    users = User.objects.order_by("username")
    return render(request, "admin/users/list.html", {
        "title": "Users",
        "users": users,
    })


@admin_required
def admin_user_new(request):
    _ensure_core_groups()
    if request.method == "POST":
        form = AdminUserCreateForm(request.POST)
        if form.is_valid():
            u = User(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                is_active=form.cleaned_data["is_active"],
            )
            u.set_password(form.cleaned_data["password"])
            u.save()

            u.groups.set(form.cleaned_data["groups"])
            u.is_staff = False  # keep out of Django admin unless you want otherwise
            u.save()

            profile, _ = StaffProfile.objects.get_or_create(user=u)
            profile.must_change_password = form.cleaned_data.get("must_change_password", True)
            profile.save()

            messages.success(request, "User created.")
            if "save_return" in request.POST:
                return redirect("admin_user_list")
            return redirect("admin_user_edit", pk=u.pk)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = AdminUserCreateForm()

    return render(request, "admin/users/form_user.html", {
        "title": "Create user",
        "form": form,
    })


@admin_required
def admin_user_edit(request, pk: int):
    _ensure_core_groups()
    user = get_object_or_404(User, pk=pk)

    if user.is_superuser and not request.user.is_superuser:
        return HttpResponseForbidden("You cannot edit a superuser.")

    profile, _ = StaffProfile.objects.get_or_create(user=user)

    if request.method == "POST":
        form = AdminUserEditForm(request.POST, instance=user)
        if form.is_valid():
            u = form.save(commit=False)
            if form.cleaned_data.get("new_password"):
                u.set_password(form.cleaned_data["new_password"])
                profile.must_change_password = True
            u.save()
            u.groups.set(form.cleaned_data["groups"])
            u.is_staff = False
            u.save()

            if "must_change_password" in form.cleaned_data:
                profile.must_change_password = form.cleaned_data["must_change_password"]
            profile.save()

            messages.success(request, "Changes saved.")
            if "save_return" in request.POST:
                return redirect("admin_user_list")
            return redirect("admin_user_edit", pk=user.pk)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = AdminUserEditForm(
            instance=user,
            initial={
                "must_change_password": profile.must_change_password,
            },
        )

    return render(request, "admin/users/form_user.html", {
        "title": f"Edit user: {user.username}",
        "form": form,
        "user_obj": user,
    })


# =========================
# Instructors (personnel)
# =========================
@admin_required
def admin_instructor_list(request):
    instructors = (
        Instructor.objects.select_related("user")
        .filter(Q(user__isnull=True) | Q(user__is_superuser=False))
        .order_by("name")
    )
    return render(request, "admin/instructors/list.html", {"instructors": instructors})


@admin_required
def admin_instructor_new(request):
    if request.method == "POST":
        form = InstructorForm(request.POST)
        if form.is_valid():
            inst = form.save()
            messages.success(request, "Instructor created.")
            if "save_return" in request.POST:
                return redirect("admin_instructor_list")
            return redirect("admin_instructor_edit", pk=inst.pk)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = InstructorForm()

    return render(request, "admin/instructors/form_instructor.html", {
        "title": "Add Instructor",
        "form": form,
        "back_url": "admin_instructor_list",
    })


@admin_required
def admin_instructor_edit(request, pk):
    inst = get_object_or_404(Instructor.objects.select_related("user"), pk=pk)

    if inst.user and inst.user.is_superuser and not request.user.is_superuser:
        return HttpResponseForbidden("You cannot edit an account attached to a superuser.")

    if request.method == "POST":
        form = InstructorForm(request.POST, instance=inst)
        if form.is_valid():
            form.save()
            messages.success(request, "Changes saved.")
            if "save_return" in request.POST:
                return redirect("admin_instructor_list")
            return redirect("admin_instructor_edit", pk=inst.pk)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = InstructorForm(instance=inst)

    return render(request, "admin/instructors/form_instructor.html", {
        "title": f"Edit Instructor — {inst.name}",
        "form": form,
        "back_url": "admin_instructor_list",
        "instructor": inst,
    })


@admin_required
@require_http_methods(["GET", "POST"])
def instructor_delete(request, pk):
    inst = get_object_or_404(Instructor, pk=pk)
    if request.method == "POST":
        inst.delete()
        messages.success(request, "Instructor deleted.")
        return redirect("admin_instructor_list")
    return render(request, "admin/confirm_delete.html", {
        "title": "Delete instructor",
        "object": inst,
        "back_url": reverse("admin_instructor_edit", args=[inst.pk]),
    })


# =========================
# Business / Booking delete (business)
# =========================
@admin_required
@require_http_methods(["GET", "POST"])
def business_delete(request, pk):
    obj = get_object_or_404(Business, pk=pk)

    if request.method == "POST":
        try:
            name = obj.name
            obj.delete()
        except ProtectedError:
            messages.error(
                request,
                f"“{obj.name}” can’t be deleted because it has related records."
            )
            return redirect("admin_business_edit", pk=obj.pk)

        messages.success(request, f"Business “{name}” deleted.")
        return redirect("admin_business_list")

    # GET -> confirm page
    return render(request, "admin/confirm_delete.html", {
        "title": "Delete business",
        "object": obj,
        "back_url": reverse("admin_business_edit", args=[obj.id]),  # uuid ok
        "post_url": reverse("admin_business_delete", args=[obj.id]),
        "warning": "This action cannot be undone.",
    })

@admin_required
@require_http_methods(["GET", "POST"])
def booking_day_registers(request, pk):
    """
    Admin page to view/edit delegates for a specific BookingDay.
    """
    day = get_object_or_404(
        BookingDay.objects.select_related("booking", "booking__course_type", "booking__business"),
        pk=pk
    )

    # Formset to edit multiple delegates quickly
    DelegateFormSet = modelformset_factory(
        model=DelegateRegister,
        fields=["name", "date_of_birth", "job_title", "employee_id", "date"],
        extra=0,
        can_delete=True,
        widgets={
            "date_of_birth": forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}),
        },
    )

    if request.method == "POST":
        formset = DelegateFormSet(request.POST, queryset=day.delegateregister_set.order_by("name"))
        if formset.is_valid():
            # Apply deletions and updates
            instances = formset.save(commit=False)
            for obj in instances:
                obj.booking_day = day
                obj.save()
            # Delete any rows flagged for deletion
            for obj in formset.deleted_objects:
                obj.delete()

            messages.success(request, "Registers saved.")
            if "save_return" in request.POST:
                return redirect("admin_booking_edit", pk=day.booking_id)
            return redirect("admin_booking_day_registers", pk=day.pk)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        formset = DelegateFormSet(queryset=day.delegateregister_set.order_by("name"))

    return render(request, "admin/booking_day_registers.html", {
        "title": "Registers",
        "day": day,
        "booking": day.booking,
        "formset": formset,
        "back_url": reverse("admin_booking_edit", args=[day.booking_id]),
    })

@admin_required
@transaction.atomic
def booking_day_registers(request, pk: int):
    """
    Admin: view & edit all delegate registers for a given BookingDay (pk is DB int/UUID).
    Uses a ModelFormSet so you can edit multiple rows at once.
    """
    day = get_object_or_404(
        BookingDay.objects.select_related(
            "booking__course_type", "booking__business", "booking__instructor"
        ),
        pk=pk,
    )

    FormSet = modelformset_factory(
        DelegateRegister,
        form=DelegateRegisterAdminForm,
        extra=0,          # no blank rows by default
        can_delete=False  # deletions go through a confirm screen
    )

    qs = DelegateRegister.objects.filter(booking_day=day).order_by("id")

    if request.method == "POST":
        formset = FormSet(request.POST, queryset=qs)
        if formset.is_valid():
            formset.save()
            messages.success(request, "Registers saved.")
            return redirect("admin_booking_day_registers", pk=day.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        formset = FormSet(queryset=qs)

    # Portable date formatting (works on Windows/macOS/Linux)
    heading_bits = []
    if day.booking and day.booking.course_type:
        heading_bits.append(day.booking.course_type.name)
    if day.date:
        heading_bits.append(date_format(day.date, "j M Y"))
    if day.booking and day.booking.business:
        heading_bits.append(day.booking.business.name)
    if day.booking and day.booking.instructor:
        heading_bits.append(f"Instructor: {day.booking.instructor.name}")
    heading = " – ".join(heading_bits) if heading_bits else "Registers"

    return render(
        request,
        "admin/booking_day_registers.html",
        {
            "title": f"Registers — {heading}",
            "day": day,
            "formset": formset,
            "back_url": (
                reverse("admin_booking_edit", args=[day.booking_id])
                if day.booking_id
                else reverse("admin_booking_list")
            ),
        },
    )



@admin_required
@require_http_methods(["GET", "POST"])
def delegate_register_delete(request, pk: int):
    reg = get_object_or_404(DelegateRegister.objects.select_related("booking_day", "instructor"), pk=pk)
    back = reverse("admin_booking_day_registers", args=[reg.booking_day_id]) if reg.booking_day_id else reverse("admin_booking_list")

    if request.method == "POST":
        reg.delete()
        messages.success(request, "Delegate removed from register.")
        return redirect(back)

    # GET — confirm screen
    return render(request, "admin/confirm_delete.html", {
        "title": "Remove delegate from register",
        "confirm_lead": "Are you sure you want to remove this delegate from the register:",
        "object": reg.name or "Unnamed delegate",
        "back_url": back,
    })


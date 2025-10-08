from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from .models import Business, CourseType, Instructor, Booking, TrainingLocation
from .forms import (
    BusinessForm,
    CourseTypeForm,
    InstructorForm,        # used for instructor/personnel screens
    AdminInstructorForm,   # if you have a specialized admin-facing form
)


# -------------------- admin guard --------------------
def is_admin(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.is_staff
        or user.groups.filter(name__iexact="admin").exists()
    )


def admin_required(view_func):
    @login_required
    def _wrapped(request, *args, **kwargs):
        if is_admin(request.user):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied
    return _wrapped


# -------------------- dashboard --------------------
@admin_required
def dashboard(request):
    return render(request, "admin/dashboard.html")


# -------------------- businesses --------------------
@admin_required
def business_list(request):
    rows = []
    for b in Business.objects.order_by("name"):
        rows.append(
            {
                "cells": [b.name, b.town or "", b.postcode or ""],
                "edit_url": reverse("admin_business_edit", args=[b.id]),
            }
        )
    ctx = {
        "title": "Businesses",
        "headers": ["Name", "Town", "Postcode"],
        "rows": rows,
        "create_url": reverse("admin_business_new"),
    }
    return render(request, "admin/list.html", ctx)


@admin_required
def business_form(request, pk=None):
    obj = get_object_or_404(Business, pk=pk) if pk else None

    if request.method == "POST":
        form = BusinessForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()  # now we have obj.id
            messages.success(request, "Changes saved.")
            if "save_return" in request.POST:
                return redirect("admin_business_list")
            return redirect("admin_business_edit", pk=obj.id)
    else:
        form = BusinessForm(instance=obj)

    locations = []
    add_location_url = None
    if obj:
        locations = TrainingLocation.objects.filter(business=obj).order_by("name")
        add_location_url = reverse("admin_location_new", args=[obj.id])

    return render(
        request,
        "admin/form_business.html",
        {
            "title": ("Edit Business" if obj else "New Business"),
            "form": form,
            "business": obj,
            "locations": locations,
            "add_location_url": add_location_url,
            "back_url": reverse("admin_business_list"),
            # GOOGLE_MAPS_API_KEY comes via context processor, no need to pass explicitly
        },
    )


# -------------------- course types --------------------
@admin_required
def course_list(request):
    rows = []
    for c in CourseType.objects.order_by("name"):
        rows.append(
            {
                "cells": [c.name, c.code, c.duration_days],
                "edit_url": reverse("admin_course_edit", args=[c.id]),
            }
        )
    ctx = {
        "title": "Course Types",
        "headers": ["Name", "Code", "Duration (days)"],
        "rows": rows,
        "create_url": reverse("admin_course_new"),
    }
    return render(request, "admin/list.html", ctx)


@admin_required
def course_form(request, pk=None):
    obj = get_object_or_404(CourseType, pk=pk) if pk else None
    if request.method == "POST":
        form = CourseTypeForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            messages.success(request, "Changes saved.")
            if "save_return" in request.POST:
                return redirect("admin_course_list")
            return redirect("admin_course_edit", pk=obj.id)
    else:
        form = CourseTypeForm(instance=obj)
    return render(
        request,
        "admin/form.html",
        {
            "title": ("Edit Course Type" if obj else "New Course Type"),
            "form": form,
            "back_url": reverse("admin_course_list"),
        },
    )


# -------------------- personnel (instructors) --------------------
@admin_required
def instructor_list(request):
    rows = []
    qs = Instructor.objects.select_related("user").order_by("name")
    for i in qs:
        rows.append(
            {
                "cells": [i.name, i.email or "", (i.user.username if i.user else "")],
                "edit_url": reverse("admin_instructor_edit", args=[i.id]),
            }
        )
    ctx = {
        "title": "Personnel",
        "headers": ["Name", "Email", "Linked User"],
        "rows": rows,
        "create_url": reverse("admin_instructor_new"),
    }
    return render(request, "admin/list.html", ctx)


def _validate_instructor_unique_user(form, instance=None):
    """
    Add a form error if selected user is already linked to another instructor.
    """
    user = form.cleaned_data.get("user")
    if not user:
        return
    qs = Instructor.objects.filter(user=user)
    if instance and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    if qs.exists():
        form.add_error(
            "user",
            "This user is already linked to another instructor.",
        )


@admin_required
def admin_instructor_new(request):
    if request.method == "POST":
        form = InstructorForm(request.POST)
        if form.is_valid():
            _validate_instructor_unique_user(form, instance=None)
            if form.errors:
                # fall through to render with errors
                pass
            else:
                inst = form.save()  # saved -> has pk
                messages.success(request, "Instructor created.")
                if "save_return" in request.POST:
                    return redirect("admin_instructor_list")
                return redirect("admin_instructor_edit", pk=inst.pk)
    else:
        form = InstructorForm()

    return render(
        request,
        "admin/instructors/form_instructor.html",
        {
            "title": "Add Personnel",
            "form": form,
            "back_url": reverse("admin_instructor_list"),
        },
    )


@admin_required
def admin_instructor_edit(request, pk):
    inst = get_object_or_404(Instructor.objects.select_related("user"), pk=pk)

    # Protect any instructor tied to a superuser
    if inst.user and inst.user.is_superuser and not request.user.is_superuser:
        return HttpResponseForbidden(
            "You cannot edit an account attached to a superuser."
        )

    if request.method == "POST":
        form = InstructorForm(request.POST, instance=inst)
        if form.is_valid():
            _validate_instructor_unique_user(form, instance=inst)
            if form.errors:
                # re-render with inline error
                pass
            else:
                inst = form.save()
                messages.success(request, "Changes saved.")
                if "save_return" in request.POST:
                    return redirect("admin_instructor_list")
                return redirect("admin_instructor_edit", pk=inst.pk)
    else:
        form = InstructorForm(instance=inst)

    return render(
        request,
        "admin/instructors/form_instructor.html",
        {
            "title": f"Edit Personnel — {inst.name}",
            "form": form,
            "back_url": reverse("admin_instructor_list"),
            "instructor": inst,
        },
    )


# -------------------- bookings --------------------
@admin_required
def booking_list(request):
    rows = []
    qs = (
        Booking.objects.select_related(
            "business", "training_location", "course_type", "instructor"
        )
        .order_by("-course_date", "start_time")
    )
    for b in qs:
        rows.append(
            {
                "cells": [
                    b.course_date,
                    b.start_time.strftime("%H:%M") if b.start_time else "",
                    b.course_type.name if b.course_type else "",
                    b.business.name if b.business else "",
                    b.training_location.name if b.training_location else "",
                    b.course_reference or "",
                ],
                "edit_url": reverse("admin_booking_edit", args=[b.id]),
            }
        )
    ctx = {
        "title": "Bookings",
        "headers": ["Date", "Start", "Course", "Business", "Location", "Ref"],
        "rows": rows,
        "create_url": reverse("admin_booking_new"),
    }
    return render(request, "admin/list.html", ctx)


@admin_required
def booking_form(request, pk=None):
    from .forms import BookingForm

    obj = get_object_or_404(Booking, pk=pk) if pk else None
    if request.method == "POST":
        form = BookingForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            messages.success(request, "Changes saved.")
            if "save_return" in request.POST:
                return redirect("admin_booking_list")
            return redirect("admin_booking_edit", pk=obj.id)
    else:
        form = BookingForm(instance=obj)
    return render(
        request,
        "admin/form.html",
        {
            "title": ("Edit Booking" if obj else "New Booking"),
            "form": form,
            "back_url": reverse("admin_booking_list"),
        },
    )


# -------------------- training locations --------------------
@admin_required
def location_new(request, business_id):
    from .forms import TrainingLocationForm

    biz = get_object_or_404(Business, pk=business_id)
    other_locations = TrainingLocation.objects.filter(business=biz).order_by("name")

    if request.method == "POST":
        form = TrainingLocationForm(request.POST)
        if form.is_valid():
            loc = form.save(commit=False)
            loc.business = biz
            loc.save()  # allow duplicate names per business
            messages.success(request, "Location saved.")
            if "save_return" in request.POST:
                return redirect("admin_business_edit", pk=biz.id)
            return redirect("admin_location_edit", pk=loc.id)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = TrainingLocationForm()

    return render(
        request,
        "admin/form_location.html",
        {
            "title": f"Add Location – {biz.name}",
            "form": form,
            "business": biz,
            "other_locations": other_locations,
            "back_url": reverse("admin_business_edit", args=[biz.id]),
            # maps key via context processor
        },
    )


@admin_required
def location_edit(request, pk):
    from .forms import TrainingLocationForm

    loc = get_object_or_404(TrainingLocation, pk=pk)
    biz = loc.business

    other_locations = (
        TrainingLocation.objects.filter(business=biz).exclude(pk=loc.pk).order_by("name")
    )

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
        form = TrainingLocationForm(instance=loc)

    return render(
        request,
        "admin/form_location.html",
        {
            "title": f"Edit Location – {biz.name}",
            "form": form,
            "business": biz,
            "other_locations": other_locations,
            "back_url": reverse("admin_business_edit", args=[biz.id]),
        },
    )


# -------------------- core groups helper --------------------
def _ensure_core_groups():
    for gname in ["admin", "instructor"]:
        Group.objects.get_or_create(name=gname)


# -------------------- simple user management (no superuser edits by admins) --------------------
@admin_required
def admin_user_list(request):
    _ensure_core_groups()
    qs = User.objects.order_by("username")
    if not request.user.is_superuser:
        qs = qs.filter(is_superuser=False)
    return render(
        request,
        "admin/users/list.html",
        {"title": "Users", "users": qs},
    )


class AdminUserCreateForm(forms.ModelForm):
    password = forms.CharField(
        label="Initial password",
        widget=forms.PasswordInput,
        required=True,
        help_text="Set an initial password.",
    )
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Tick one or more roles (e.g., admin, instructor).",
    )

    class Meta:
        model = User
        fields = ["username", "email", "password", "is_active", "groups"]


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

    class Meta:
        model = User
        fields = ["username", "email", "is_active", "groups"]


@admin_required
def admin_user_new(request):
    _ensure_core_groups()
    if request.method == "POST":
        form = AdminUserCreateForm(request.POST)
        if form.is_valid():
            groups = list(form.cleaned_data["groups"])
            is_admin_group = any(g.name.lower() == "admin" for g in groups)

            u = User(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                is_active=form.cleaned_data["is_active"],
                is_staff=is_admin_group,  # only admin group members get staff
            )
            u.set_password(form.cleaned_data["password"])
            u.save()
            u.groups.set(groups)

            messages.success(request, "User created.")
            if "save_return" in request.POST:
                return redirect("admin_user_list")
            return redirect("admin_user_edit", pk=u.pk)
    else:
        form = AdminUserCreateForm()

    return render(
        request,
        "admin/users/form_user.html",
        {"title": "Create user", "form": form},
    )


@admin_required
def admin_user_edit(request, pk: int):
    _ensure_core_groups()
    user = get_object_or_404(User, pk=pk)

    # non-superusers cannot edit superusers
    if user.is_superuser and not request.user.is_superuser:
        return HttpResponseForbidden("You cannot edit a superuser account.")

    if request.method == "POST":
        form = AdminUserEditForm(request.POST, instance=user)
        if form.is_valid():
            groups = list(form.cleaned_data["groups"])
            is_admin_group = any(g.name.lower() == "admin" for g in groups)

            u = form.save(commit=False)
            # keep staff in sync with admin group membership
            u.is_staff = is_admin_group or u.is_staff
            new_pw = form.cleaned_data.get("new_password")
            if new_pw:
                u.set_password(new_pw)
            u.save()
            u.groups.set(groups)

            messages.success(request, "Changes saved.")
            if "save_return" in request.POST:
                return redirect("admin_user_list")
            return redirect("admin_user_edit", pk=user.pk)
    else:
        form = AdminUserEditForm(instance=user)

    return render(
        request,
        "admin/users/form_user.html",
        {"title": f"Edit user: {user.username}", "form": form, "user_obj": user},
    )

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from .models import Business, CourseType, Instructor, Booking, TrainingLocation, StaffProfile
from .forms import BusinessForm, CourseTypeForm, TrainingLocationForm, InstructorForm


# ---------- helpers / guards ----------
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

def _ensure_core_groups():
    for gname in ("admin", "instructor"):
        Group.objects.get_or_create(name=gname)


# ---------- Admin dashboard ----------
@admin_required
def dashboard(request):
    return render(request, "admin/dashboard.html")


# ---------- Businesses ----------
@admin_required
def business_list(request):
    rows = []
    for b in Business.objects.order_by("name"):
        rows.append({
            "cells": [b.name, b.town or "", b.postcode or ""],
            "edit_url": reverse("admin_business_edit", args=[b.id]),
        })
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
            obj = form.save()
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

    return render(request, "admin/form_business.html", {
        "title": ("Edit Business" if obj else "New Business"),
        "form": form,
        "business": obj,
        "locations": locations,
        "add_location_url": add_location_url,
        "back_url": reverse("admin_business_list"),
    })


# ---------- Location add/edit ----------
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
        form = TrainingLocationForm(instance=loc)

    return render(request, "admin/form_location.html", {
        "title": f"Edit Location – {biz.name}",
        "form": form,
        "business": biz,
        "other_locations": other_locations,
        "back_url": reverse("admin_business_edit", args=[biz.id]),
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
    })


# ---------- Course Types ----------
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
    return render(request, "admin/form.html", {
        "title": ("Edit Course Type" if obj else "New Course Type"),
        "form": form,
        "back_url": reverse("admin_course_list"),
    })


# ---------- Bookings (simple list/form stubs remain unchanged) ----------
@admin_required
def booking_list(request):
    rows = []
    qs = (Booking.objects
          .select_related("business", "training_location", "course_type", "instructor")
          .order_by("-course_date", "start_time"))
    for b in qs:
        rows.append({
            "cells": [
                b.course_date,
                b.start_time.strftime("%H:%M") if b.start_time else "",
                b.course_type.name if b.course_type else "",
                b.business.name if b.business else "",
                b.training_location.name if b.training_location else "",
                b.course_reference or "",
            ],
            "edit_url": reverse("admin_booking_edit", args=[b.id]),
        })
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
    return render(request, "admin/form.html", {
        "title": ("Edit Booking" if obj else "New Booking"),
        "form": form,
        "back_url": reverse("admin_booking_list"),
    })


# ======================================================================
#                           USER MANAGEMENT
# ======================================================================

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
                is_staff=True,   # keep if you want staff to access /admin
            )
            u.set_password(form.cleaned_data["password"])
            u.save()
            u.groups.set(form.cleaned_data["groups"])

            # ensure StaffProfile & set must_change_password
            profile, _ = StaffProfile.objects.get_or_create(user=u)
            profile.must_change_password = form.cleaned_data.get("must_change_password", True)
            profile.save()

            messages.success(request, "User created.")
            if "save_return" in request.POST:
                return redirect("admin_user_list")
            return redirect("admin_user_edit", pk=u.pk)
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

    # Optional: don’t allow editing an account attached to a superuser unless you’re a superuser
    if user.is_superuser and not request.user.is_superuser:
        return HttpResponseForbidden("You cannot edit a superuser.")

    profile, _ = StaffProfile.objects.get_or_create(user=user)

    if request.method == "POST":
        form = AdminUserEditForm(request.POST, instance=user)
        if form.is_valid():
            u = form.save(commit=False)
            if form.cleaned_data.get("new_password"):
                u.set_password(form.cleaned_data["new_password"])
                profile.must_change_password = True  # on reset, force change
            u.save()
            u.groups.set(form.cleaned_data["groups"])

            # apply the checkbox explicitly too
            if "must_change_password" in form.cleaned_data:
                profile.must_change_password = form.cleaned_data["must_change_password"]
            profile.save()

            messages.success(request, "Changes saved.")
            if "save_return" in request.POST:
                return redirect("admin_user_list")
            return redirect("admin_user_edit", pk=user.pk)
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


# ---------- Personnel (Instructors) ----------
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
        form = InstructorForm(instance=inst)

    return render(request, "admin/instructors/form_instructor.html", {
        "title": f"Edit Instructor — {inst.name}",
        "form": form,
        "back_url": "admin_instructor_list",
        "instructor": inst,
    })

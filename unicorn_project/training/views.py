from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db.models import Q
from django.http import JsonResponse, HttpResponseForbidden, FileResponse
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET
from .models import Business, TrainingLocation, CourseType, Instructor, Booking, BookingDay, StaffProfile, DelegateRegister, FeedbackResponse
from .forms import  BookingForm, InstructorForm, InstructorProfileForm, DelegateRegisterForm, FeedbackForm
from datetime import timedelta, datetime
from reportlab.lib.pagesizes import A4, portrait
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
import uuid, io


# --- helpers --------------------------------------------------

def is_instructor_user(user):
    return user.is_authenticated and (
        user.groups.filter(name__iexact="instructor").exists()
        or hasattr(user, "instructor")
    )

def get_instructor_for_user(user):
    """
    Resolve the Instructor profile for this user.
    If you allow multiple mappings, adjust here; otherwise one-to-one.
    """
    try:
        if hasattr(user, "instructor") and user.instructor:
            return user.instructor
    except Instructor.DoesNotExist:
        pass
    # fallback: name/email match, if you’ve used that pattern in your data
    return Instructor.objects.filter(user=user).first()

# --- home redirect --------------------------------------------

def home(request):
    if request.user.is_authenticated:
        if request.user.is_superuser or request.user.groups.filter(name__iexact="admin").exists():
            return redirect("app_admin_dashboard")
        if is_instructor_user(request.user):
            return redirect("instructor_bookings")
    return render(request, "home.html")



def _must_change_password_gate(request):
    if not request.user.is_authenticated:
        return None
    prof = getattr(request.user, "staff_profile", None)
    if prof and prof.must_change_password and request.path != "/accounts/password_change/":
        return redirect("password_change")
    return None

def _parse_yyyy_mm_dd(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None

def _instructors_for_date(course: CourseType, day_date):
    """
    Return instructors who are delivering *this* course on the given date,
    by traversing Booking -> BookingDay(date=day_date).
    """
    if not (course and day_date):
        return Instructor.objects.none()
    return (
        Instructor.objects
        .filter(bookings__course_type=course, bookings__days__date=day_date)
        .distinct()
        .order_by("name")
    )

def ensure_groups():
    Group.objects.get_or_create(name='admin')
    Group.objects.get_or_create(name='instructor')

def roles_for(user):
    ensure_groups()
    r=[]
    if user.is_authenticated:
        if user.groups.filter(name='admin').exists(): r.append('admin')
        if user.groups.filter(name='instructor').exists(): r.append('instructor')
        if user.is_superuser: r.append('superuser')
    return r

@require_GET
def public_delegate_instructors_api(request):
    """
    JSON:  /register/instructors?ct=EFAAW&date=2025-10-21
    Returns [{id, name}, ...] for the instructor select.
    """
    code = (request.GET.get("ct") or request.GET.get("code") or "").strip()
    date_str = (request.GET.get("date") or request.GET.get("d") or "").strip()
    day_date = _parse_yyyy_mm_dd(date_str) or timezone.localdate()

    course = CourseType.objects.filter(code__iexact=code).first()
    qs = _instructors_for_date(course, day_date) if course else Instructor.objects.none()
    data = [{"id": i.id, "name": i.name} for i in qs]
    return JsonResponse({"instructors": data})

def public_delegate_register(request):
    """
    Public delegate register page.
    - Optional ?ct=<COURSE_CODE> to preselect a course
    - Optional ?date=YYYY-MM-DD to preselect the date
    - Instructor list is restricted to instructors who have a booking
      for the selected course and date.
    """
    # 1) Resolve course from ?ct=<code> or posted course_id
    course = None
    ct_code = (request.GET.get("ct") or "").strip()
    if ct_code:
        course = CourseType.objects.filter(code__iexact=ct_code).first()

    # For the dropdown when no QR is used
    course_types = CourseType.objects.order_by("name")

    # 2) Initial date (from querystring if present)
    initial = {}
    if request.GET.get("date"):
        initial["date"] = request.GET["date"]

    form = DelegateRegisterForm(request.POST or None, initial=initial)

    # 3) Build instructors list (depends on course + date)
    instructors = []
    bound_date = form.data.get("date") if form.is_bound else initial.get("date")
    if course and bound_date:
        instructors = (
            Instructor.objects
            .filter(
                bookings__course_type=course,       # NOTE plural 'bookings__'
                bookings__days__date=bound_date
            )
            .distinct()
            .order_by("name")
        )

    if request.method == "POST" and form.is_valid():
        # Save delegate and attach to matching BookingDay if we can find one
        delegate = form.save(commit=False)

        # The form has an FK 'instructor' field; use it and also try to attach a BookingDay
        inst = delegate.instructor
        bd = None
        if course and inst and form.cleaned_data.get("date"):
            bd = (
                BookingDay.objects
                .filter(
                    booking__course_type=course,
                    booking__instructor=inst,
                    date=form.cleaned_data["date"],
                )
                .first()
            )
        delegate.booking_day = bd
        delegate.save()

        messages.success(request, "Thank you — you’re on the register.")
        # Redirect to the same page (keeps ?ct=... to stay on the same course)
        return redirect(request.get_full_path())

    # 4) Render (make sure we point at the correct template path)
    return render(
        request,
        "public/delegate_register.html",   # <— correct location
        {
            "form": form,
            "course": course,
            "course_types": course_types,
            "instructors": instructors,
        },
    )

@login_required
def switch_role(request, role):
    if role in roles_for(request.user):
        request.session['current_role']=role
        messages.success(request, f"Switched to {role}")
    else:
        messages.error(request, "You don't have that role.")
    return redirect('home')

@login_required
def home(request):
    if 'current_role' not in request.session:
        r = roles_for(request.user)
        if r: request.session['current_role']=r[0]
    return render(request,'home.html',{})

# Admin app
@login_required
def app_admin_dashboard(request):
    if not (request.user.is_superuser or request.user.groups.filter(name='admin').exists()):
        return HttpResponseForbidden()
    bookings = Booking.objects.select_related('business','training_location','course_type','instructor').order_by('-course_date')[:50]
    return render(request,'admin_app/dashboard.html',{'bookings':bookings})

@login_required
def app_admin_booking_new(request):
    if not (request.user.is_superuser or request.user.groups.filter(name='admin').exists()):
        return HttpResponseForbidden()
    form = BookingForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        b = form.save()
        n = int(float(b.course_duration_days or b.course_type.duration_days) + 0.999)
        from datetime import timedelta
        for i in range(1,n+1):
            BookingDay.objects.create(booking=b, day_no=i, day_date=b.course_date+timedelta(days=i-1), start_time=b.start_time)
        messages.success(request,"Booking created")
        return redirect('app_admin_booking_detail', pk=b.id)
    return render(request,'admin_app/booking_form.html',{'form':form})

@login_required
def app_admin_booking_detail(request, pk):
    if not (request.user.is_superuser or request.user.groups.filter(name='admin').exists()):
        return HttpResponseForbidden()
    b = get_object_or_404(Booking, pk=pk)
    days = b.days.order_by('day_no')
    return render(request,'admin_app/booking_detail.html',{'booking':b,'days':days})

# Instructor app
@login_required
def instructor_dashboard(request):
    if is_instructor_user(request.user):
        return redirect("instructor_bookings")
    return redirect("home")

# helper for human label + bootstrap class
_STATUS_MAP = {
    "scheduled":        ("Scheduled", "badge bg-info text-dark"),
    "in_progress":      ("In progress", "badge bg-dark"),
    "awaiting_closure": ("Awaiting instructor closure", "badge", "background-color:#6f42c1;color:#fff"),
    "completed":        ("Completed", "badge bg-success"),
    "cancelled":        ("Cancelled", "badge bg-warning text-dark"),
}

@login_required
def instructor_bookings(request):
    """
    Landing page for instructors: upcoming courses for the logged-in instructor.
    """
    today = timezone.localdate()

    # Find the instructor record for this user
    inst = Instructor.objects.filter(user=request.user).first()
    if not inst:
        # No instructor linked — show an empty page with a friendly message
        return render(request, "instructor/bookings.html", {
            "title": "My bookings",
            "rows": [],
            "empty_reason": "Your account isn’t linked to an instructor profile yet.",
        })

    qs = (Booking.objects
          .select_related("course_type", "business", "training_location")
          .filter(instructor=inst, course_date__gte=today)
          .order_by("course_date", "start_time"))

    rows = []
    for b in qs:
        # ----- NEW: precompute label & badge style so template is simple
        label, cls, *opt_style = _STATUS_MAP.get(b.status or "", ("", "badge bg-secondary"))
        rows.append({
            "id":           b.id,
            "date":         b.course_date,
            "start":        b.start_time.strftime("%H:%M") if b.start_time else "",
            "course":       b.course_type.name if b.course_type else "",
            "business":     b.business.name if b.business else "",
            "location":     b.training_location.name if b.training_location else "",
            "ref":          b.course_reference or "",
            "status_label": label,
            "status_cls":   cls,
            "status_style": opt_style[0] if opt_style else "",
        })

    return render(request, "instructor/bookings.html", {
        "title": "My bookings",
        "rows": rows,
        "empty_reason": "" if rows else "You have no upcoming bookings.",
    })

@login_required
def instructor_profile(request):
    try:
        inst = Instructor.objects.get(user=request.user)
    except Instructor.DoesNotExist:
        inst = None

    if request.method == "POST":
        form = InstructorProfileForm(request.POST, instance=inst)
        if form.is_valid():
            obj = form.save(commit=False)
            # lock to current user
            obj.user = request.user
            obj.save()
            messages.success(request, "Profile saved.")
            return redirect("instructor_profile")
    else:
        form = InstructorProfileForm(instance=inst)

    return render(request, "instructor/profile.html", {
        "title": "My Profile",
        "form": form,
    })

# Public attendance
def public_attendance(request, booking_day_id):
    bday = get_object_or_404(BookingDay, pk=booking_day_id)
    if request.method=='POST':
        form = AttendanceForm(request.POST)
        if form.is_valid():
            att = form.save(commit=False)
            att.booking_day = bday
            att.save()
            return render(request,'public/attendance_success.html',{'booking_day':bday})
    else:
        form = AttendanceForm()
    return render(request,'public/attendance.html',{'form':form,'booking_day':bday})

# API
@login_required
def api_locations_by_business(request):
    bid = request.GET.get('business')
    data=[]
    if bid:
        for x in TrainingLocation.objects.filter(business_id=bid).order_by('name'):
            data.append({'id': str(x.id), 'name': f"{x.name} — {x.address_line or ''} {x.postcode or ''}"})
    return JsonResponse({'data':data})

# Switch role view
@login_required
def switch_role(request, role):
    role = role.lower()
    # only allow switching to roles the user actually has
    if role == "admin" and (request.user.is_superuser or request.user.groups.filter(name__iexact="admin").exists()):
        request.session["active_role"] = "admin"
        messages.success(request, "Switched to Admin.")
    elif role == "instructor" and request.user.groups.filter(name__iexact="instructor").exists():
        request.session["active_role"] = "instructor"
        messages.success(request, "Switched to Instructor.")
    else:
        messages.error(request, "You don't have that role.")
    return redirect("home")

# Instructor my bookings view
@login_required
def instructor_bookings(request):
    # Require the user to be linked to an Instructor record
    try:
        instructor = Instructor.objects.select_related('user').get(user=request.user)
    except Instructor.DoesNotExist:
        messages.error(request, "Your user account isn’t linked to an Instructor profile yet.")
        return redirect('instructor_dashboard')  # or 'home'

    bookings = (
        Booking.objects
        .select_related('business', 'training_location', 'course_type')
        .filter(instructor=instructor)
        .order_by('-course_date', 'start_time')
    )
    return render(request, 'instructor/bookings.html', {
        'bookings': bookings,
        'instructor': instructor,
    })

@login_required
def instructor_booking_detail(request, pk):
    """
    Detail page for a single booking, visible only to its assigned instructor.
    """
    iinst = get_instructor_for_user(request.user)
    if not inst:
        return HttpResponseForbidden("Not an instructor account.")

    booking = get_object_or_404(
        Booking.objects.select_related("business", "training_location", "course_type", "instructor"),
        pk=pk,
    )
    if booking.instructor_id != inst.id:
        return HttpResponseForbidden("This booking is not assigned to you.")

    # Convenient status label
    status_labels = dict(getattr(Booking, "STATUS_CHOICES", []))
    status_label = status_labels.get(booking.status, booking.status)

    # Include the course days
    days = booking.days.all().order_by("date")

    return render(request, "instructor/booking_detail.html", {
        "title": "Booking details",
        "booking": booking,
        "status_label": status_label,
        "days": days,
        "today": timezone.localdate(),
    })

def _user_is_instructor(user) -> bool:
    # Safe check: user linked to Instructor?
    try:
        return hasattr(user, "instructor") and user.instructor is not None
    except Instructor.DoesNotExist:
        return False

@login_required
def post_login_router(request):
    user = request.user

    # 1) Admin/staff ALWAYS go to admin dashboard
    if user.is_superuser or user.is_staff:
        return redirect("app_admin_dashboard")

    # 2) Respect explicit role choice in session (but admin already took precedence)
    role = request.session.get("role")
    if role == "admin":
        return redirect("app_admin_dashboard")
    if role == "instructor" and _user_is_instructor(user):
        return redirect("instructor_bookings")

    # 3) Sensible defaults
    if _user_is_instructor(user):
        return redirect("instructor_bookings")

    # If neither admin nor instructor, drop them at admin (or your public home)
    return redirect("app_admin_dashboard")

def _resolve_course_type(value):
    if not value:
        return None
    # Try UUID first
    try:
        return CourseType.objects.filter(id=uuid.UUID(str(value))).first()
    except Exception:
        pass
    # Fall back to course code (case-insensitive)
    return CourseType.objects.filter(code__iexact=str(value)).first()

def _parse_date_flexible(s: str):
    if not s:
        return None
    d = parse_date(s)  # expects YYYY-MM-DD
    if d:
        return d
    # Try dd/mm/yyyy
    if "/" in s:
        try:
            dd, mm, yyyy = s.split("/")
            return parse_date(f"{yyyy}-{int(mm):02d}-{int(dd):02d}")
        except Exception:
            return None
    return None

def public_feedback_instructors_api(request):
    """
    Returns instructors who are delivering the given course on the given date.
    Query params:
      - course: course code (e.g. FAAW) or course UUID
      - date:   YYYY-MM-DD (required for filtering)
    If either parameter is missing, returns an empty list (no noisy fallback).
    """
    course_param = (request.GET.get("course") or "").strip()
    date_str     = (request.GET.get("date") or "").strip()

    # Resolve course by code OR UUID
    ct = None
    if course_param:
        ct = CourseType.objects.filter(code__iexact=course_param).first()
        if not ct:
            try:
                uuid.UUID(course_param)
                ct = CourseType.objects.filter(pk=course_param).first()
            except Exception:
                ct = None

    # Parse date flexibly: YYYY-MM-DD or dd/mm/yyyy
    the_date = None
    if date_str:
        the_date = parse_date(date_str)
        if not the_date and "/" in date_str:
            try:
                dd, mm, yyyy = date_str.split("/")
                the_date = parse_date(f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}")
            except Exception:
                the_date = None

    # Strict behaviour: only return matches when both pieces are present
    qs = Instructor.objects.none()
    if ct and the_date:
        qs = (
            Instructor.objects
            .filter(
                bookings__course_type=ct,
                bookings__days__date=the_date,
            )
            .distinct()
            .order_by("name")
        )

    return JsonResponse({
        "options": [{"id": str(i.id), "name": i.name} for i in qs]
    })


def _resolve_course_type(q):
    if not q:
        return None
    q = q.strip()
    ct = CourseType.objects.filter(code__iexact=q).first()
    if ct:
        return ct
    try:
        uuid.UUID(q)
        return CourseType.objects.filter(pk=q).first()
    except Exception:
        return None

def _parse_flexible_date(s):
    if not s:
        return None
    d = parse_date(s)
    if d:
        return d
    if "/" in s:
        try:
            dd, mm, yyyy = s.split("/")
            return parse_date(f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}")
        except Exception:
            return None
    return None

def public_feedback_form(request):
    """
    Public course feedback form. Supports optional prefill via:
      ?course=<code or UUID>&date=YYYY-MM-DD&instructor=<UUID>
    """
    course_q = request.GET.get("course") or ""
    prefilled_course = _resolve_course_type(course_q)

    # Initials: date (today unless provided) and instructor (optional)
    init = {
        "date": _parse_flexible_date(request.GET.get("date") or "") or timezone.localdate()
    }
    inst_q = request.GET.get("instructor") or ""
    if inst_q:
        try:
            init["instructor"] = Instructor.objects.get(pk=inst_q)
        except Instructor.DoesNotExist:
            pass

    form = FeedbackForm(request.POST or None, initial=init)

    # If course isn’t prefilled, user must choose it; otherwise set hidden initial
    form.fields["course_type"].required = not bool(prefilled_course)
    if prefilled_course:
        form.fields["course_type"].initial = prefilled_course.id

    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        course = prefilled_course or cd.get("course_type")

        # Create the feedback row
        FeedbackResponse.objects.create(
            course_type = course,
            date        = cd.get("date"),
            instructor  = cd.get("instructor"),

            # ratings
            overall_rating       = cd.get("overall_rating"),
            prior_knowledge      = cd.get("prior_knowledge"),
            post_knowledge       = cd.get("post_knowledge"),
            q_purpose_clear      = cd.get("q_purpose_clear"),
            q_personal_needs     = cd.get("q_personal_needs"),
            q_exercises_useful   = cd.get("q_exercises_useful"),
            q_structure          = cd.get("q_structure"),
            q_pace               = cd.get("q_pace"),
            q_content_clear      = cd.get("q_content_clear"),
            q_instructor_knowledge = cd.get("q_instructor_knowledge"),
            q_materials_quality  = cd.get("q_materials_quality"),
            q_books_quality      = cd.get("q_books_quality"),
            q_venue_suitable     = cd.get("q_venue_suitable"),
            q_benefit_at_work    = cd.get("q_benefit_at_work"),
            q_benefit_outside    = cd.get("q_benefit_outside"),

            # free text + contact
            comments       = cd.get("comments") or "",
            wants_callback = cd.get("wants_callback") or False,
            contact_name   = cd.get("contact_name") or "",
            contact_email  = cd.get("contact_email") or "",
            contact_phone  = cd.get("contact_phone") or "",
        )

        messages.success(request, "Thanks for your feedback!")
        return redirect("public_feedback_thanks")

    return render(
        request,
        "public/feedback_form.html",
        {"form": form, "course_type": prefilled_course},
    )


def public_feedback_pdf(request, pk):
    """Minimal single-response PDF so the route works."""
    fb = get_object_or_404(
        FeedbackResponse.objects.select_related("course_type", "instructor"),
        pk=pk
    )

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=portrait(A4))
    W, H = portrait(A4)
    left, top = 15*mm, H - 15*mm

    y = top
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(W/2, y, f"{fb.course_type.code} — Course Feedback")
    y -= 8*mm
    c.setFont("Helvetica", 10)
    c.drawString(left, y, f"Date: {fb.date.strftime('%d %b %Y')}")
    y -= 5*mm
    c.drawString(left, y, f"Instructor: {fb.instructor.name if fb.instructor else '—'}")
    y -= 10*mm

    c.setFont("Helvetica", 9)
    c.drawString(left, y, f"Prior knowledge: {fb.prior_knowledge or '—'} / 5")
    y -= 5*mm
    c.drawString(left, y, f"Post knowledge:  {fb.post_knowledge  or '—'} / 5")
    y -= 8*mm
    c.drawString(left, y, f"Comments: {(fb.comments or '')[:300]}")
    y -= 12*mm

    c.setFont("Helvetica", 8)
    c.drawString(left, 10*mm, "Unicorn Fire & Safety Solutions, Unicorn House, 6 Salendine, Shrewsbury, SY1 3XJ: info@unicornsafety.co.uk: 01743 360211")

    c.save()
    buf.seek(0)
    return FileResponse(buf, as_attachment=True, filename=f"feedback_{fb.course_type.code}_{fb.date:%Y%m%d}.pdf")

def public_feedback_thanks(request):
    """Simple thank-you page after feedback submission."""
    return render(request, "public/feedback_thanks.html")


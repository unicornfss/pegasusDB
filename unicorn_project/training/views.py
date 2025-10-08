from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from .models import Business, TrainingLocation, CourseType, Instructor, Booking, BookingDay
from .forms import AttendanceForm, BookingForm, InstructorForm, InstructorProfileForm
from datetime import timedelta

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
    if not (request.user.is_superuser or request.user.groups.filter(name='instructor').exists()):
        return HttpResponseForbidden()
    instr = Instructor.objects.filter(user=request.user).first()
    bookings = Booking.objects.filter(instructor=instr).select_related('business','training_location','course_type') if instr else []
    return render(request,'instructor/dashboard.html',{'bookings':bookings})

@login_required
def instructor_booking_detail(request, pk):
    if not (request.user.is_superuser or request.user.groups.filter(name='instructor').exists()):
        return HttpResponseForbidden()
    instr = Instructor.objects.filter(user=request.user).first()
    b = get_object_or_404(Booking, pk=pk)
    if not request.user.is_superuser and (not instr or b.instructor_id != instr.id):
        return HttpResponseForbidden()
    days = b.days.order_by('day_no')
    return render(request,'instructor/booking_detail.html',{'booking':b,'days':days})

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

from django.contrib import admin
from . import models
@admin.register(models.Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display=('name','town','postcode','contact_name','telephone','email')
@admin.register(models.TrainingLocation)
class TrainingLocationAdmin(admin.ModelAdmin):
    list_display=('name','business','town','postcode')
    list_filter=('business',)
@admin.register(models.CourseType)
class CourseTypeAdmin(admin.ModelAdmin):
    list_display=('name','code','duration_days','default_course_fee','default_instructor_fee','has_written_exam','has_online_exam')
@admin.register(models.Instructor)
class InstructorAdmin(admin.ModelAdmin):
    list_display=('name','email','telephone','user')
class BookingDayInline(admin.TabularInline):
    model=models.BookingDay
    extra=0
@admin.register(models.Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display=('course_reference','course_type','business','training_location','instructor','course_date','start_time')
    list_filter=('business','course_type','instructor')
    inlines=[BookingDayInline]
@admin.register(models.Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display=('delegate_name','delegate_email','booking_day','result','signed_at')
# superuser-only gate is handled by default (only staff can access admin; mark superuser for full access)

from decimal import Decimal as D
from django import forms
from django.contrib import admin
from .models import (
    Business, TrainingLocation, CourseType,
    Instructor, Booking, BookingDay, Attendance
)

class CourseTypeAdminForm(forms.ModelForm):
    D_CHOICES = [(D("0.5"), "0.5"), (D("1.0"), "1"), (D("2.0"), "2"),
                 (D("3.0"), "3"), (D("4.0"), "4"), (D("5.0"), "5")]
    duration_days = forms.ChoiceField(choices=D_CHOICES, label="Duration (days)")
    def clean_duration_days(self):
        return D(str(self.cleaned_data["duration_days"]))
    class Meta:
        model = CourseType
        fields = "__all__"

class BookingDayInline(admin.TabularInline):
    model = BookingDay
    extra = 0
    fields = ("date", "start_time", "day_code")
    readonly_fields = ("day_code",)
    ordering = ("date",)

@admin.register(CourseType)
class CourseTypeAdmin(admin.ModelAdmin):
    form = CourseTypeAdminForm
    list_display = (
        "name", "code", "duration_days",
        "default_course_fee", "default_instructor_fee",
        "has_exam",
    )
    search_fields = ("name", "code")

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display  = ("name", "town", "postcode")
    search_fields = ("name", "town", "postcode")

@admin.register(TrainingLocation)
class TrainingLocationAdmin(admin.ModelAdmin):
    list_display  = ("name", "business", "town", "postcode")
    list_filter   = ("business",)
    search_fields = ("name", "business__name", "town", "postcode")

@admin.register(Instructor)
class InstructorAdmin(admin.ModelAdmin):
    list_display  = ("name", "email", "user")
    search_fields = ("name", "email", "user__username")

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display  = ("course_date", "course_type", "business", "training_location", "course_reference")
    list_filter   = ("course_type", "business")
    search_fields = ("course_reference", "business__name", "training_location__name", "course_type__name")
    inlines = [BookingDayInline]

@admin.register(BookingDay)
class BookingDayAdmin(admin.ModelAdmin):
    list_display  = ("booking", "date", "start_time", "day_code")
    list_filter   = ("date",)
    search_fields = ("day_code", "booking__course_reference")

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display  = ("booking_day", "delegate_name", "signed_at")
    list_filter   = ("booking_day__date",)
    search_fields = ("delegate_name", "booking_day__day_code")

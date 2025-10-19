from decimal import Decimal as D
from django import forms
from django.contrib import admin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from import_export.admin import ImportExportModelAdmin

from .models import (
    Business, TrainingLocation, CourseType,
    Instructor, Booking, BookingDay, Attendance, CourseCompetency,
    Invoice, InvoiceItem
)

# ---------- Forms ----------

class CourseTypeAdminForm(forms.ModelForm):
    D_CHOICES = [
        (D("0.5"), "0.5"),
        (D("1.0"), "1"),
        (D("2.0"), "2"),
        (D("3.0"), "3"),
        (D("4.0"), "4"),
        (D("5.0"), "5"),
    ]
    duration_days = forms.ChoiceField(choices=D_CHOICES, label="Duration (days)")

    def clean_duration_days(self):
        return D(str(self.cleaned_data["duration_days"]))

    class Meta:
        model = CourseType
        fields = "__all__"

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    fields = ("description", "amount")   # <- your actual fields
    # no readonly_fields needed

# ---------- Inlines ----------

class BookingDayInline(admin.TabularInline):
    model = BookingDay
    extra = 0
    fields = ("date", "start_time", "day_code")
    readonly_fields = ("day_code",)
    ordering = ("date",)


# ---------- Resources for Import/Export ----------

class CourseTypeResource(resources.ModelResource):
    class Meta:
        model = CourseType
        import_id_fields = ["id"]  # you use UUIDs; keep them stable
        fields = (
            "id",
            "code",
            "name",
            "duration_days",
            "has_exam",
            "default_course_fee",
            "default_instructor_fee",
        )


class CourseCompetencyResource(resources.ModelResource):
    course_type = fields.Field(
        column_name="course_type",
        attribute="course_type",
        widget=ForeignKeyWidget(CourseType, "code"),  # import/export via CourseType.code
    )

    class Meta:
        model = CourseCompetency
        import_id_fields = ["id"]
        fields = (
            "id",
            "course_type",  # as code in CSV/XLSX
            "code",
            "name",
            "description",
            "sort_order",
            "is_active",
        )


class InstructorResource(resources.ModelResource):
    class Meta:
        model = Instructor
        import_id_fields = ["id"]
        fields = (
            "id",
            "name",
            "email",
            "telephone",
            "address_line",
            "town",
            "postcode",
        )


# ---------- Admins (single registration each) ----------

@admin.register(CourseType)
class CourseTypeAdmin(ImportExportModelAdmin):
    form = CourseTypeAdminForm
    resource_class = CourseTypeResource
    list_display = (
        "name",
        "code",
        "duration_days",
        "default_course_fee",
        "default_instructor_fee",
        "has_exam",
    )
    search_fields = ("name", "code")


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "town", "postcode")
    search_fields = ("name", "town", "postcode")


@admin.register(TrainingLocation)
class TrainingLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "town", "postcode")
    list_filter = ("business",)
    search_fields = ("name", "business__name", "town", "postcode")


@admin.register(Instructor)
class InstructorAdmin(ImportExportModelAdmin):
    resource_class = InstructorResource
    list_display = ("name", "email", "user")
    search_fields = ("name", "email", "user__username")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("course_date", "course_type", "business", "training_location", "course_reference")
    list_filter = ("course_type", "business")
    search_fields = ("course_reference", "business__name", "training_location__name", "course_type__name")
    inlines = [BookingDayInline]


@admin.register(BookingDay)
class BookingDayAdmin(admin.ModelAdmin):
    list_display = ("booking", "date", "start_time", "day_code")
    list_filter = ("date",)
    search_fields = ("day_code", "booking__course_reference")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("booking_day", "delegate_name", "signed_at")
    list_filter = ("booking_day__date",)
    search_fields = ("delegate_name", "booking_day__day_code")


@admin.register(CourseCompetency)
class CourseCompetencyAdmin(ImportExportModelAdmin):
    resource_class = CourseCompetencyResource
    list_display = ("course_type", "code", "name", "sort_order", "is_active")
    list_filter = ("course_type", "is_active")
    search_fields = ("code", "name", "course_type__code", "course_type__name")

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "booking",          # OneToOne to Booking
        "business_name",    # derived from booking.business.name
        "instructor",
        "status",
        "invoice_date",
        "total",            # @property on model
        "created_at",
    )
    list_filter = ("status", "invoice_date", "created_at")
    search_fields = (
        "booking__course_reference",
        "booking__business__name",
        "instructor__name",
    )
    date_hierarchy = "created_at"
    inlines = [InvoiceItemInline]
    readonly_fields = ("created_at", "updated_at")

    def business_name(self, obj):
        b = getattr(getattr(obj.booking, "business", None), "name", None)
        return b or "—"
    business_name.short_description = "Business"

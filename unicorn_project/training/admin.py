# unicorn_project/training/admin.py

from decimal import Decimal as D
from datetime import timedelta

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin

from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from import_export.admin import ImportExportModelAdmin

from .models import (
    AccidentReport, Business, Resource, TrainingLocation, CourseType,
    Personnel, Booking, BookingDay, Attendance, CourseCompetency,
    FeedbackResponse, Invoice, InvoiceItem, MetaSetting,
    Exam, ExamAttempt, ExamAttemptAnswer, ExamQuestion, ExamAnswer,
    LogoOverride
)

Instructor = Personnel
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

# ---------- Inlines ----------

class BookingDayInline(admin.TabularInline):
    model = BookingDay
    extra = 0
    fields = ("date", "start_time", "day_code")
    readonly_fields = ("day_code",)
    ordering = ("date",)

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    fields = ("description", "amount")

# ---------- Import/Export resources ----------

class CourseTypeResource(resources.ModelResource):
    class Meta:
        model = CourseType
        import_id_fields = ["id"]
        fields = (
            "id", "code", "name", "duration_days",
            "has_exam", "default_course_fee", "default_instructor_fee",
        )

class CourseCompetencyResource(resources.ModelResource):
    course_type = fields.Field(
        column_name="course_type",
        attribute="course_type",
        widget=ForeignKeyWidget(CourseType, "code"),
    )
    class Meta:
        model = CourseCompetency
        import_id_fields = ["id"]
        fields = ("id", "course_type", "code", "name", "description", "sort_order", "is_active")

class InstructorResource(resources.ModelResource):
    class Meta:
        model = Instructor
        import_id_fields = ["id"]
        fields = ("id", "name", "email", "telephone", "address_line", "town", "postcode")

# ---------- Admins ----------

@admin.register(CourseType)
class CourseTypeAdmin(ImportExportModelAdmin):
    form = CourseTypeAdminForm
    resource_class = CourseTypeResource
    list_display = ("name", "code", "duration_days", "default_course_fee", "default_instructor_fee", "has_exam")
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
    list_display = ("booking", "business_name", "instructor", "status", "invoice_date", "total", "created_at")
    list_filter = ("status", "invoice_date", "created_at")
    search_fields = ("booking__course_reference", "booking__business__name", "instructor__name")
    date_hierarchy = "created_at"
    inlines = [InvoiceItemInline]
    readonly_fields = ("created_at", "updated_at")

    def business_name(self, obj):
        b = getattr(getattr(obj.booking, "business", None), "name", None)
        return b or "—"
    business_name.short_description = "Business"

# ----- Exam / Attempt admin -----

class ExamAttemptAnswerInline(admin.TabularInline):
    model = ExamAttemptAnswer
    extra = 0
    # Drop autocomplete_fields to avoid requiring separate admins
    readonly_fields = ("is_correct",)
    fields = ("question", "answer", "is_correct")
    ordering = ("question__order", "question_id")

class ExamAttemptInline(admin.TabularInline):
    model = ExamAttempt
    extra = 0
    show_change_link = True
    autocomplete_fields = ("instructor",)

    # any computed columns MUST be in readonly_fields
    readonly_fields = (
        "display_name",
        "score_display",
        "result_display",
        "started_at_admin",
        "completed_at_admin",
    )

    fields = (
        "exam_date",
        "display_name",        # computed
        "date_of_birth",
        "instructor",
        "score_display",       # computed
        "result_display",      # computed
        "started_at_admin",    # computed wrapper
        "completed_at_admin",  # computed wrapper
    )
    ordering = ("-exam_date", "-started_at", "-pk")

    # robust delegate name
    def display_name(self, obj):
        return (
            getattr(obj, "name", None)
            or getattr(obj, "delegate_name", None)
            or " ".join(
                x for x in [
                    getattr(obj, "first_name", "") or "",
                    getattr(obj, "last_name", "") or "",
                ] if x
            ).strip()
            or "—"
        )
    display_name.short_description = "Delegate"

    def score_display(self, obj: ExamAttempt):
        correct = obj.answers.filter(is_correct=True).count()
        total = getattr(getattr(obj, "exam", None), "questions", None)
        total = total.count() if total is not None else 0
        return f"{correct}/{total}"
    score_display.short_description = "Score"

    def result_display(self, obj: ExamAttempt):
        res = (getattr(obj, "result", "") or "").lower()
        label, css = "Fail", "red"
        if res == "pass":
            label, css = "Pass", "green"
        elif res == "viva":
            label, css = "Viva", "darkorange"
        return mark_safe(f'<b style="color:{css}">{label}</b>')
    result_display.short_description = "Result"

    def started_at_admin(self, obj):
        return getattr(obj, "started_at", None)
    started_at_admin.short_description = "Started at"

    def completed_at_admin(self, obj):
        # supports either .completed_at or .finished_at
        return getattr(obj, "completed_at", None) or getattr(obj, "finished_at", None)
    completed_at_admin.short_description = "Completed at"

@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    inlines = [ExamAttemptAnswerInline]

    list_display = (
        "id", "exam", "exam_date", "display_name", "date_of_birth",
        "instructor", "score_admin", "result_badge",
        "started_at_admin", "completed_at_admin",
    )
    list_filter = ("exam", "exam__course_type", "exam_date", "instructor")
    search_fields = (
        "name", "delegate_name", "first_name", "last_name",
        "exam__exam_code", "exam__title", "instructor__name",
    )
    ordering = ("-started_at", "-pk")
    autocomplete_fields = ("exam", "instructor")

    # All computed values must be in readonly_fields (use callables for viva*)
    readonly_fields = (
        "display_name",
        "score_admin",
        "result_badge",
        "seconds_total_admin",
        "seconds_used_admin",
        "started_at_admin",
        "completed_at_admin",
        "expires_at",
        # viva shown via callables -> avoids admin system check errors
        "viva_decided_at_admin",
        "viva_decided_by_admin",
    )

    fieldsets = (
        ("Attempt", {
            "fields": (
                "exam", "exam_date", "instructor",
                "display_name", "date_of_birth",
            )
        }),
        ("Timing", {
            "fields": (
                "seconds_total_admin", "seconds_used_admin",
                "started_at_admin", "completed_at_admin",
                "expires_at",
            )
        }),
        ("Outcome", {
            "fields": (
                "result_badge",
                "viva_notes",
                "viva_decided_at_admin",
                "viva_decided_by_admin",
            )
        }),
    )

    # ----- Display helpers -----
    def display_name(self, obj):
        return (
            getattr(obj, "name", None)
            or getattr(obj, "delegate_name", None)
            or " ".join(
                x for x in [
                    getattr(obj, "first_name", "") or "",
                    getattr(obj, "last_name", "") or "",
                ] if x
            ).strip()
            or "—"
        )
    display_name.short_description = "Delegate"

    def score_admin(self, obj):
        correct = obj.answers.filter(is_correct=True).count()
        total_rel = getattr(getattr(obj, "exam", None), "questions", None)
        total = total_rel.count() if total_rel is not None else 0
        return f"{correct}/{total}"
    score_admin.short_description = "Score"

    def result_badge(self, obj):
        res = (getattr(obj, "result", "") or "").lower()
        label = "Fail"; css = "background:#dc3545;color:#fff;"     # red
        if res == "pass":
            label, css = "Pass", "background:#198754;color:#fff;"  # green
        elif res == "viva":
            label, css = "Viva", "background:#ffc107;color:#111;"  # yellow
        return format_html(
            '<span style="padding:2px 8px;border-radius:12px;{}">{}</span>',
            css, label
        )
    result_badge.short_description = "Result"

    def seconds_total_admin(self, obj):
        v = getattr(obj, "seconds_total", None)
        if isinstance(v, int):
            return v
        limit = getattr(getattr(obj, "exam", None), "time_limit_seconds", None)
        return limit if isinstance(limit, int) else "—"
    seconds_total_admin.short_description = "Seconds total"

    def seconds_used_admin(self, obj):
        v = getattr(obj, "seconds_used", None)
        if isinstance(v, int):
            return v
        start = getattr(obj, "started_at", None)
        end = getattr(obj, "completed_at", None) or getattr(obj, "finished_at", None)
        if start and end:
            return int((end - start).total_seconds())
        return "—"
    seconds_used_admin.short_description = "Seconds used"

    def started_at_admin(self, obj):
        return getattr(obj, "started_at", None)
    started_at_admin.short_description = "Started at"
    started_at_admin.admin_order_field = "started_at"

    def completed_at_admin(self, obj):
        return getattr(obj, "completed_at", None) or getattr(obj, "finished_at", None)
    completed_at_admin.short_description = "Completed at"
    completed_at_admin.admin_order_field = "completed_at"

    # ----- Viva read-only callables (safe for admin system check) -----
    def viva_decided_at_admin(self, obj):
        return getattr(obj, "viva_decided_at", None)
    viva_decided_at_admin.short_description = "Viva decided at"
    viva_decided_at_admin.admin_order_field = "viva_decided_at"

    def viva_decided_by_admin(self, obj):
        user = getattr(obj, "viva_decided_by", None)
        # if your User has .name use that, else fallback to username / repr
        return getattr(user, "name", None) or getattr(user, "username", None) or user
    viva_decided_by_admin.short_description = "Viva decided by"
    viva_decided_by_admin.admin_order_field = "viva_decided_by"

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    inlines = [ExamAttemptInline]

    list_display = ("course_type", "sequence", "exam_code", "title",
                    "viva_enabled_admin", "viva_percent_admin",
                    "pass_mark_percent", "attempts_count")
    # Only use real fields in list_filter to avoid system check errors
    list_filter = ("course_type",)
    search_fields = ("exam_code", "title", "course_type__name", "course_type__code")
    ordering = ("course_type__name", "sequence")

    def attempts_count(self, obj: Exam):
        return ExamAttempt.objects.filter(exam=obj).count()
    attempts_count.short_description = "Submissions"

    # Safe accessors for optional viva fields
    def viva_enabled_admin(self, obj):
        v = getattr(obj, "viva_enabled", None)
        if v is None:
            return "—"
        return "Yes" if bool(v) else "No"
    viva_enabled_admin.short_description = "Viva enabled"

    def viva_percent_admin(self, obj):
        v = getattr(obj, "viva_percent", None)
        return f"{v}%" if v is not None else "—"
    viva_percent_admin.short_description = "Viva %"

class ExamQuestionResource(resources.ModelResource):
    # Use exam_code for the FK so CSVs are easy to read/edit
    exam = fields.Field(
        column_name="exam_code",
        attribute="exam",
        widget=ForeignKeyWidget(Exam, "exam_code"),
    )

    class Meta:
        model = ExamQuestion
        fields = ("id", "exam", "order", "text")
        export_order = ("id", "exam", "order", "text")


class ExamAnswerResource(resources.ModelResource):
    # Reference the parent question by its primary key.
    # (This keeps imports unambiguous. You can export first to get the IDs.)
    question = fields.Field(
        column_name="question_id",
        attribute="question",
        widget=ForeignKeyWidget(ExamQuestion, "id"),
    )

    class Meta:
        model = ExamAnswer
        fields = ("id", "question", "order", "text", "is_correct")
        export_order = ("id", "question", "order", "text", "is_correct")


# ---------- Inlines & Admins ----------

class ExamAnswerInline(admin.TabularInline):
    model = ExamAnswer
    extra = 1
    fields = ("order", "text", "is_correct")
    ordering = ("order", "id")


@admin.register(ExamQuestion)
class ExamQuestionAdmin(ImportExportModelAdmin):
    """Questions visible as a standalone table + import/export."""
    resource_classes = [ExamQuestionResource]
    list_display = ("id", "exam", "order", "short_text", "answers_count")
    list_filter = ("exam",)
    search_fields = ("text", "exam__exam_code", "exam__title", "exam__course_type__name")
    ordering = ("exam__exam_code", "order", "id")
    autocomplete_fields = ("exam",)
    inlines = [ExamAnswerInline]

    @admin.display(description="Question")
    def short_text(self, obj: ExamQuestion):
        t = (obj.text or "").strip()
        return (t[:80] + "…") if len(t) > 80 else t or "—"

    @admin.display(description="# Answers")
    def answers_count(self, obj: ExamQuestion):
        # avoids N+1 if you want: annotate in a custom queryset; for now quick count()
        return obj.answers.count()


@admin.register(ExamAnswer)
class ExamAnswerAdmin(ImportExportModelAdmin):
    """Answers also available as a flat table + import/export."""
    resource_classes = [ExamAnswerResource]
    list_display = ("id", "question", "order", "short_text", "is_correct")
    list_filter = ("question__exam", "is_correct")
    search_fields = (
        "text",
        "question__text",
        "question__exam__exam_code",
        "question__exam__title",
        "question__exam__course_type__name",
    )
    ordering = ("question__exam__exam_code", "question__order", "order", "id")
    autocomplete_fields = ("question",)

    @admin.display(description="Answer")
    def short_text(self, obj: ExamAnswer):
        t = (obj.text or "").strip()
        return (t[:80] + "…") if len(t) > 80 else t or "—"
# ---------------------------------------------------------------------------

@admin.register(AccidentReport)
class AccidentReportAdmin(admin.ModelAdmin):
    list_display = ("date", "time", "location", "injured_name", "first_aider_name", "reporter_name")
    search_fields = ("injured_name", "first_aider_name", "reporter_name", "location")
    list_filter = ("date",)

@admin.register(LogoOverride)
class LogoOverrideAdmin(admin.ModelAdmin):
    list_display = ("file_name", "active", "starts_at", "ends_at", "priority", "reason")
    list_filter = ("active",)
    search_fields = ("file_name", "reason")

class PersonnelInline(admin.StackedInline):
    model = Personnel
    can_delete = False
    verbose_name_plural = "Personnel details"
    readonly_fields = ("two_factor_status_display",)
    
    def two_factor_status_display(self, obj):
        """Display 2FA status in the inline."""
        if obj.totp_secret:
            return format_html('<span style="color: green;">✓ 2FA Enabled</span>')
        else:
            return format_html('<span style="color: red;">✗ 2FA Disabled</span>')
    two_factor_status_display.short_description = "Two-Factor Authentication"


class CustomUserAdmin(UserAdmin):
    """
    Custom User admin that:
    - Uses email in list display & ordering
    - Shows Personnel details inline on the same screen
    """
    inlines = [PersonnelInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        ("Permissions", {
            "fields": (
                "is_active", "is_staff", "is_superuser",
                "groups", "user_permissions",
            )
        }),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2"),
        }),
    )

    list_display = ("email", "first_name", "last_name", "is_staff", "two_factor_status")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("email",)
    actions = ["disable_2fa", "reset_password"]

    @admin.display(description="2FA Status", boolean=True)
    def two_factor_status(self, obj):
        """Display 2FA status for the user."""
        try:
            return bool(obj.personnel.totp_secret)
        except Personnel.DoesNotExist:
            return False

    @admin.action(description="Disable 2FA for selected users")
    def disable_2fa(self, request, queryset):
        """Admin action to disable 2FA for selected users."""
        from django.utils.crypto import get_random_string
        from unicorn_project.training.utils.passwords import send_initial_password_email
        
        updated = 0
        for user in queryset:
            try:
                personnel = user.personnel
                if personnel.totp_secret:
                    personnel.totp_secret = None
                    personnel.save(update_fields=['totp_secret'])
                    updated += 1
            except Personnel.DoesNotExist:
                continue
        
        if updated:
            self.message_user(
                request,
                f"Successfully disabled 2FA for {updated} user{'s' if updated != 1 else ''}.",
            )
        else:
            self.message_user(
                request,
                "No users had 2FA enabled.",
            )

    @admin.action(description="Reset passwords for selected users")
    def reset_password(self, request, queryset):
        """Admin action to reset passwords for selected users."""
        from django.utils.crypto import get_random_string
        from unicorn_project.training.utils.passwords import send_initial_password_email
        
        updated = 0
        for user in queryset:
            try:
                personnel = user.personnel
                # Generate new password
                temp_password = get_random_string(12)
                
                # Set the new password
                user.set_password(temp_password)
                user.is_active = True
                user.save(update_fields=['password', 'is_active'])
                
                # Set must_change_password flag
                personnel.must_change_password = True
                personnel.save(update_fields=['must_change_password'])
                
                # Send email
                send_initial_password_email(personnel, temp_password)
                updated += 1
            except Personnel.DoesNotExist:
                continue
        
        if updated:
            self.message_user(
                request,
                f"Successfully reset passwords for {updated} user{'s' if updated != 1 else ''}. "
                f"Temporary passwords have been emailed.",
            )
        else:
            self.message_user(
                request,
                "No users were updated.",
            )


# Replace Django’s default User admin with your custom version
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

admin.site.register(User, CustomUserAdmin)

@admin.register(MetaSetting)
class MetaSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value")
    search_fields = ("key",)

@admin.register(FeedbackResponse)
class FeedbackResponseAdmin(admin.ModelAdmin):
    list_display = ("date", "course_type", "instructor", "overall_rating", "wants_callback")
    list_filter = ("course_type", "date", "wants_callback")
    search_fields = ("contact_name", "contact_email", "comments")

@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "course_type", "category", "is_active")
    list_filter = ("course_type", "category", "is_active")
    search_fields = ("title", "description")
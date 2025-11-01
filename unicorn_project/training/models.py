# unicorn_project/training/models.py
import uuid
from datetime import date
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from django.utils import timezone


# =========================
# Core / Reference Models
# =========================

class Business(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)

    address_line = models.CharField(max_length=255, blank=True, null=True)
    town         = models.CharField(max_length=255, blank=True, null=True)
    postcode     = models.CharField(max_length=32,  blank=True, null=True)

    contact_name = models.CharField(max_length=255, blank=True, null=True)
    telephone    = models.CharField(max_length=64,  blank=True, null=True)
    email        = models.EmailField(blank=True, null=True)

    # used to keep a matching default TrainingLocation in sync
    add_as_training_location = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class TrainingLocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="training_locations")
    name = models.CharField(max_length=255)

    address_line = models.CharField(max_length=255, blank=True, null=True)
    town         = models.CharField(max_length=255, blank=True, null=True)
    postcode     = models.CharField(max_length=32,  blank=True, null=True)

    contact_name = models.CharField(max_length=255, blank=True, null=True)
    telephone    = models.CharField(max_length=64,  blank=True, null=True)
    email        = models.EmailField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.business.name})"


class CourseType(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    duration_days = models.DecimalField(
        max_digits=3, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("10.0"))],
        default=Decimal("1.0"),
    )

    # defaults that prefill a Booking (but remain editable there)
    default_course_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    default_instructor_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # exams
    has_exam = models.BooleanField(
        default=False,
        verbose_name="This course contains theoretical exam(s)",
    )
    number_of_exams = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Required if 'This course contains theoretical exam(s)' is ticked.",
        validators=[MinValueValidator(1)],
    )

    def clean(self):
        # Enforce conditional requirement
        if self.has_exam and not self.number_of_exams:
            raise ValidationError({"number_of_exams": "Please enter how many exams this course has (whole number ≥ 1)."})
        # Keep field tidy when exams are disabled
        if not self.has_exam:
            self.number_of_exams = None

    class Meta:
        constraints = [
            # DB-level safety: either no exams -> number_of_exams must be NULL,
            # or has_exam -> number_of_exams >= 1
            models.CheckConstraint(
                name="course_type_exam_consistency",
                check=Q(has_exam=False, number_of_exams__isnull=True) | Q(has_exam=True, number_of_exams__gte=1),
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Instructor(models.Model):
    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.PROTECT, related_name="instructor")

    name     = models.CharField(max_length=255)
    address_line = models.CharField(max_length=255, blank=True)
    town         = models.CharField(max_length=120, blank=True)
    postcode     = models.CharField(max_length=12,  blank=True)

    telephone = models.CharField(max_length=32, blank=True)
    email     = models.EmailField(unique=True)

    bank_sort_code       = models.CharField(max_length=16, blank=True)
    bank_account_number  = models.CharField(max_length=20, blank=True)
    name_on_account      = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return self.name


# =========================
# Operational Models
# =========================

class Booking(models.Model):
    """
    A booking of a course for a business/location.
    course_reference is generated as: <course_type.code>-<6 char A/Z/0-9>, unique.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    business          = models.ForeignKey(Business,         on_delete=models.CASCADE, related_name="bookings")
    training_location = models.ForeignKey(TrainingLocation, on_delete=models.CASCADE, related_name="bookings")
    course_type       = models.ForeignKey(CourseType,       on_delete=models.PROTECT, related_name="bookings")
    instructor        = models.ForeignKey(Instructor,       on_delete=models.SET_NULL, null=True, blank=True, related_name="bookings")

    course_date = models.DateField()
    start_time  = models.TimeField(null=True, blank=True, default=None)
    booking_notes = models.TextField(blank=True)

    # generated reference
    course_reference = models.CharField(max_length=40, unique=True, blank=True)

    # fees (prefilled from CourseType, but editable)
    course_fee     = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    instructor_fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # snapshot of location’s contact (prefilled, editable)
    contact_name   = models.CharField(max_length=200, blank=True)
    telephone      = models.CharField(max_length=50, blank=True)
    email          = models.EmailField(blank=True)

    # models.py  (inside Booking)
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("in_progress", "In progress"),
        ("awaiting_closure", "Awaiting instructor closure"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                            default="scheduled", db_index=True)

    cancel_reason = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # optional convenience
    def is_cancelled(self):
        return self.status == "cancelled"

    comments      = models.TextField(blank=True)
    closure_register_manual = models.BooleanField(default=False)
    closure_assess_manual   = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.course_reference or "(pending)"

    def _generate_unique_reference(self):
        import random, string
        base = (self.course_type.code if self.course_type_id else "COURSE").upper()
        for _ in range(80):
            suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            ref = f"{base}-{suffix}"
            if not Booking.objects.filter(course_reference=ref).exists():
                return ref
        raise ValueError("Could not generate unique course reference")

    def save(self, *args, **kwargs):
        if not self.course_reference:
            self.course_reference = self._generate_unique_reference()
        super().save(*args, **kwargs)


class BookingDay(models.Model):
    booking = models.ForeignKey('Booking', on_delete=models.CASCADE, related_name='days')
    date = models.DateField()  # (you already renamed from day_date)
    start_time = models.TimeField(blank=True, null=True)
    end_time   = models.TimeField(null=True, blank=True)
    # Make it safe to migrate without a one-off default:
    day_code = models.CharField(max_length=64, blank=True, default='', db_index=True)

    def save(self, *args, **kwargs):
        # auto-generate if missing
        if not self.day_code and self.booking_id and self.date:
            # assumes Booking has course_reference
            self.day_code = f"{self.date.strftime('%Y%m%d')}-{self.booking.course_reference}"
        super().save(*args, **kwargs)



class Attendance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking_day   = models.ForeignKey(BookingDay, on_delete=models.CASCADE, related_name="attendances")
    delegate_name = models.CharField(max_length=200)
    delegate_email = models.EmailField(blank=True)
    result = models.CharField(max_length=50, blank=True)
    notes  = models.TextField(blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.delegate_name} @ {self.booking_day}"


# =========================
# Staff profile / signals
# =========================

class StaffProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    must_change_password = models.BooleanField(default=False)

    def __str__(self):
        return f"Profile({self.user.username})"


@receiver(post_save, sender=User)
def ensure_staff_profile(sender, instance, created, **kwargs):
    if created:
        StaffProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=Business)
def sync_business_training_location(sender, instance: Business, created, **kwargs):
    """
    Keep a default TrainingLocation in sync with Business when the
    'Add as training location' toggle is changed.
    """
    name = instance.name
    if instance.add_as_training_location:
        loc = TrainingLocation.objects.filter(business=instance, name=name).order_by("id").first()
        if not loc:
            loc = TrainingLocation(business=instance, name=name)
        # copy fields
        loc.address_line = instance.address_line
        loc.town         = instance.town
        loc.postcode     = instance.postcode
        loc.contact_name = instance.contact_name
        loc.telephone    = instance.telephone
        loc.email        = instance.email
        loc.save()
    else:
        TrainingLocation.objects.filter(business=instance, name=name).delete()

class CourseOutcome(models.TextChoices):
    PENDING = "pending", "Pending"
    PASS    = "pass",    "Pass"
    FAIL    = "fail",    "Fail"
    DNF     = "dnf",     "Did not finish"

class DelegateRegister(models.Model):
    class HealthStatus(models.TextChoices):
        FIT            = "fit", "I am fit to take part in all the mental and physical aspects of today's course."
        AGREED         = "agreed_adjustments", "I have a mental or physical impairment that I have discussed with the instructor already and am happy to continue with agreed alterations."
        WILL_DISCUSS   = "will_discuss", "I have a mental or physical impairment and will discuss this with the instructor."
        NOT_FIT        = "not_fit", "I do not feel mentally and/or physically well enough to take part in training today and will speak with my own manager about this."

    name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    job_title = models.CharField(max_length=100)
    employee_id = models.CharField(max_length=50, blank=True)
    date = models.DateField(default=timezone.localdate)  # forced to 'today' server-side
    instructor = models.ForeignKey("Instructor", on_delete=models.PROTECT)
    health_status = models.CharField(
        max_length=24,
        choices=HealthStatus.choices,
        default=HealthStatus.FIT,
    )
    outcome = models.CharField(
        max_length=8,
        choices=CourseOutcome.choices,
        default=CourseOutcome.PENDING,
    )
    notes = models.TextField(blank=True)
    booking_day = models.ForeignKey("BookingDay", on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Proper case the name
        if self.name:
            self.name = " ".join(w.capitalize() for w in self.name.strip().split())
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.date})"

    def health_badge_class(self) -> str:
        return {
            self.HealthStatus.FIT: "bg-success",
            self.HealthStatus.AGREED: "bg-warning text-dark",
            self.HealthStatus.WILL_DISCUSS: "",  # we'll style inline orange
            self.HealthStatus.NOT_FIT: "bg-danger",
        }.get(self.health_status, "bg-secondary")

class CourseCompetency(models.Model):
    course_type = models.ForeignKey(
        CourseType,
        on_delete=models.CASCADE,
        related_name="competencies",
    )
    code = models.CharField(
        max_length=32, blank=True,
        help_text="Optional short code (e.g. C1, ABC-01)."
    )
    name = models.CharField(
        max_length=200,
        help_text="What the delegate must be able to do (visible to instructors)."
    )
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0, help_text="Controls display order.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["course_type", "name"],
                name="uniq_competency_name_per_course_type",
            ),
        ]

    def __str__(self):
        return f"{self.course_type.code or self.course_type.name}: {self.name}"

class AssessmentLevel(models.TextChoices):
    NOT_ASSESSED = "na", "Not assessed"
    NEEDS_IMPROVEMENT = "ni", "Needs improvement"
    COMPETENT = "c", "Competent"
    EXCEEDED = "e", "Exceeded"

class CompetencyAssessment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    register = models.ForeignKey("DelegateRegister", on_delete=models.CASCADE, related_name="assessments")
    course_competency = models.ForeignKey("CourseCompetency", on_delete=models.PROTECT, related_name="assessments")
    level = models.CharField(max_length=2, choices=AssessmentLevel.choices, default=AssessmentLevel.NOT_ASSESSED)
    notes = models.CharField(max_length=255, blank=True)
    assessed_by = models.ForeignKey("Instructor", on_delete=models.PROTECT)
    assessed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("register", "course_competency")
        ordering = ["register_id", "course_competency_id"]

# --- Feedback ---------------------------------------------------------------
class FeedbackResponse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_type = models.ForeignKey(CourseType, on_delete=models.PROTECT, related_name="feedback")
    date = models.DateField(default=timezone.localdate)  # auto "today"
    instructor = models.ForeignKey(Instructor, on_delete=models.SET_NULL, null=True, blank=True, related_name="feedback")

    # 1–5 ratings
    prior_knowledge = models.PositiveSmallIntegerField(null=True, blank=True)   # "Level of knowledge prior to course"
    post_knowledge  = models.PositiveSmallIntegerField(null=True, blank=True)   # "Level of knowledge post course"

    # Course objectives & content
    q_purpose_clear     = models.PositiveSmallIntegerField(null=True, blank=True)
    q_personal_needs    = models.PositiveSmallIntegerField(null=True, blank=True)
    q_exercises_useful  = models.PositiveSmallIntegerField(null=True, blank=True)

    # Presentation
    q_structure         = models.PositiveSmallIntegerField(null=True, blank=True)
    q_pace              = models.PositiveSmallIntegerField(null=True, blank=True)
    q_content_clear     = models.PositiveSmallIntegerField(null=True, blank=True)
    q_instructor_knowledge = models.PositiveSmallIntegerField(null=True, blank=True)
    q_materials_quality = models.PositiveSmallIntegerField(null=True, blank=True)
    q_books_quality     = models.PositiveSmallIntegerField(null=True, blank=True)

    # Venue
    q_venue_suitable    = models.PositiveSmallIntegerField(null=True, blank=True)

    # Summary
    q_benefit_at_work   = models.PositiveSmallIntegerField(null=True, blank=True)
    q_benefit_outside   = models.PositiveSmallIntegerField(null=True, blank=True)

    # Overall
    overall_rating = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Delegate’s overall 1–5 rating"
    )

    # Free text
    comments = models.TextField(blank=True)

    # Contact follow-up
    wants_callback = models.BooleanField(default=False)
    contact_name   = models.CharField(max_length=200, blank=True)
    contact_email  = models.EmailField(blank=True)
    contact_phone  = models.CharField(max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def overall_average(self):
        vals = [
            v for v in [
                self.prior_knowledge, self.post_knowledge,
                self.q_purpose_clear, self.q_personal_needs, self.q_exercises_useful,
                self.q_structure, self.q_pace, self.q_content_clear, self.q_instructor_knowledge,
                self.q_materials_quality, self.q_books_quality, self.q_venue_suitable,
                self.q_benefit_at_work, self.q_benefit_outside
            ] if v is not None
        ]
        return round(sum(vals)/len(vals), 2) if vals else None

    def __str__(self):
        ref = self.course_type.code if self.course_type_id else "Course"
        return f"Feedback {ref} {self.date} ({self.id})"

class Invoice(models.Model):
    STATUS_CHOICES = [
        ("draft", "Awaiting completion and sending"),
        ("sent", "Sent"),
        ("viewed", "Viewed"),
        ("paid", "Paid"),
        ("awaiting_review", "Awaiting instructor review"),
        ("rejected", "Rejected"),
    ]
    booking = models.OneToOneField("Booking", on_delete=models.CASCADE, related_name="invoice")
    instructor = models.ForeignKey("Instructor", on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    invoice_date = models.DateField(null=True, blank=True)
    instructor_ref = models.CharField(max_length=100, blank=True)

    # Bank details (pre-filled from Instructor; editable on draft)
    account_name = models.CharField(max_length=200, blank=True)
    sort_code = models.CharField(max_length=20, blank=True)
    account_number = models.CharField(max_length=30, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_locked(self):
        # cannot edit after sent unless admin sets awaiting_review
        return self.status not in ("draft", "awaiting_review")

    @property
    def base_amount(self):
        return self.booking.instructor_fee or 0

    @property
    def total(self):
        add = sum(x.amount for x in self.items.all())
        return (self.base_amount or 0) + add


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

# models.py

class Exam(models.Model):
    course_type = models.ForeignKey("CourseType", on_delete=models.CASCADE, related_name="exams")
    sequence = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200, blank=True)

    exam_code = models.CharField(
        max_length=40,
        unique=True,
        editable=False,
        db_index=True,
        blank=True,
    )

    # --- NEW: pass mark + viva options ---
    pass_mark_percent = models.PositiveSmallIntegerField(
        default=80,  # was 70; now default 80%
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Passing threshold as a percentage (1–100).",
    )
    allow_viva = models.BooleanField(default=False)
    viva_pass_percent = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="If enabled, viva threshold (must be between pass−10 and pass−1).",
    )
    # -------------------------------------

    class Meta:
        unique_together = ("course_type", "sequence")
        ordering = ["sequence"]

    def _computed_exam_code(self) -> str:
        base = (self.course_type.code or "").upper()
        return f"{base}{int(self.sequence):02d}"

    def _computed_title(self) -> str:
        return f"{self.course_type.name}: Exam {int(self.sequence):02d}"

    # Validation for viva rules
    def clean(self):
        super().clean()

        p = int(self.pass_mark_percent or 0)

        if not self.allow_viva:
            # If viva disabled, ensure field is cleared
            self.viva_pass_percent = None
            return

        # Viva enabled → enforce range [pass−10, pass−1]
        min_viva = max(1, p - 10)
        max_viva = max(1, p - 1)

        # If not provided, default to pass−10 (clamped just in case)
        if self.viva_pass_percent is None:
            self.viva_pass_percent = min(max_viva, max(min_viva, p - 10))
            return

        v = int(self.viva_pass_percent)
        if not (min_viva <= v <= max_viva):
            raise ValidationError({
                "viva_pass_percent": (
                    f"Viva must be between {min_viva}% and {max_viva}% "
                    f"(given {v}%, pass mark is {p}%)."
                )
            })

    def save(self, *args, **kwargs):
        if self.course_type_id and self.sequence:
            self.exam_code = self._computed_exam_code()

            auto_title = self._computed_title()
            simple_default = f"Exam {int(self.sequence)}"

            if not self.pk:
                if not (self.title or "").strip() or (self.title or "").strip() == simple_default:
                    self.title = auto_title
            else:
                try:
                    old = type(self).objects.get(pk=self.pk)
                    old_auto = f"{old.course_type.name}: Exam {int(old.sequence):02d}"
                    if (self.title or "").strip() in ("", simple_default, old_auto):
                        self.title = auto_title
                except type(self).DoesNotExist:
                    if not (self.title or "").strip() or (self.title or "").strip() == simple_default:
                        self.title = auto_title

        # Run validators (incl. viva rules) before saving
        self.full_clean()
        super().save(*args, **kwargs)

class ExamQuestion(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveIntegerField(default=1)
    text = models.TextField()

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"Q{self.order}: {self.text[:60]}"


class ExamAnswer(models.Model):
    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE, related_name="answers")
    order = models.PositiveIntegerField(default=1)
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            # at most one correct answer per question (DB-level)
            models.UniqueConstraint(
                fields=["question"],
                condition=Q(is_correct=True),
                name="unique_correct_answer_per_question",
            )
        ]

    def __str__(self):
        return f"{self.text}{' (correct)' if self.is_correct else ''}"
    
from django.utils import timezone

class ExamAttempt(models.Model):
    exam = models.ForeignKey("Exam", on_delete=models.CASCADE, related_name="attempts")
    # Snapshot of who started (from the start page)
    delegate_name = models.CharField(max_length=120)
    date_of_birth = models.DateField()
    instructor = models.ForeignKey("Instructor", null=True, blank=True, on_delete=models.SET_NULL)
    exam_date = models.DateField()

    started_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    score_correct = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)

    passed = models.BooleanField(default=False)
    viva_eligible = models.BooleanField(default=False)

    viva_notes = models.TextField(blank=True)
    viva_decided_at = models.DateTimeField(null=True, blank=True)
    viva_decided_by = models.ForeignKey(
        "Instructor",  # or settings.AUTH_USER_MODEL if you prefer
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="viva_decisions",
    )

    def is_viva_pending(self) -> bool:
        return (self.result or "").lower() == "viva" and not self.viva_decided_at

    def remaining_seconds(self) -> int:
        if self.finished_at:
            return 0
        now = timezone.now()
        return max(0, int((self.expires_at - now).total_seconds()))

class ExamAttemptAnswer(models.Model):
    attempt = models.ForeignKey("ExamAttempt", on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey("ExamQuestion", on_delete=models.CASCADE)
    answer = models.ForeignKey("ExamAnswer", null=True, blank=True, on_delete=models.SET_NULL)
    is_correct = models.BooleanField(default=False)

    class Meta:
        unique_together = ("attempt", "question")

class ExamAttempt(models.Model):
    exam = models.ForeignKey("Exam", on_delete=models.CASCADE, related_name="attempts")
    delegate_name = models.CharField(max_length=120)
    date_of_birth = models.DateField()
    instructor = models.ForeignKey("Instructor", null=True, blank=True, on_delete=models.SET_NULL)
    exam_date = models.DateField()

    started_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    score_correct = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)

    passed = models.BooleanField(default=False)
    viva_eligible = models.BooleanField(default=False)

    retake_authorised = models.BooleanField(default=False)
    retake_authorised_until = models.DateTimeField(null=True, blank=True)

    @property
    def attempt_number(self) -> int:
        qs = (ExamAttempt.objects
              .filter(exam=self.exam,
                      delegate_name__iexact=self.delegate_name,
                      date_of_birth=self.date_of_birth)
              .order_by("started_at", "pk")
              .values_list("pk", flat=True))
        try:
            return list(qs).index(self.pk) + 1
        except ValueError:
            return 1  # fallback if not in the list

class ExamAttemptAnswer(models.Model):
    attempt = models.ForeignKey("ExamAttempt", on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey("ExamQuestion", on_delete=models.CASCADE)
    answer = models.ForeignKey("ExamAnswer", null=True, blank=True, on_delete=models.SET_NULL)
    is_correct = models.BooleanField(default=False)

    class Meta:
        unique_together = ("attempt", "question")

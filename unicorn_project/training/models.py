# unicorn_project/training/models.py
import uuid
from datetime import date
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator 
from django.db import models
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
        max_digits=3, decimal_places=1,
        validators=[MinValueValidator(Decimal("0.5")), MaxValueValidator(Decimal("5.0"))],
        default=Decimal("1.0"),
    )

    # defaults that prefill a Booking (but remain editable there)
    default_course_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    default_instructor_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # single flag for “this course has any theoretical exam(s)”
    has_exam = models.BooleanField(
        default=False,
        verbose_name="This course contains theoretical exam(s)"
    )

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
    date = models.DateField(default=timezone.localdate)  # we will force this to 'today' server-side
    instructor = models.ForeignKey("Instructor", on_delete=models.PROTECT)
    health_status = models.CharField(
        max_length=24,
        choices=HealthStatus.choices,
        default=HealthStatus.FIT,
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

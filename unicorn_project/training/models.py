from django.db import models
from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from django.utils import timezone
import uuid

class Business(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    address_line = models.CharField(max_length=255, blank=True, null=True)
    town = models.CharField(max_length=255, blank=True, null=True)
    postcode = models.CharField(max_length=32, blank=True, null=True)
    contact_name = models.CharField(max_length=255, blank=True, null=True)
    telephone = models.CharField(max_length=64, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    add_as_training_location = models.BooleanField(default=False)

    def __str__(self):
        return self.name

class TrainingLocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='training_locations')
    name = models.CharField(max_length=255)
    address_line = models.CharField(max_length=255, blank=True, null=True)
    town = models.CharField(max_length=255, blank=True, null=True)
    postcode = models.CharField(max_length=32, blank=True, null=True)
    contact_name = models.CharField(max_length=255, blank=True, null=True)
    telephone = models.CharField(max_length=64, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.business.name})"

class CourseType(models.Model):
    id=models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name=models.CharField(max_length=255)
    code=models.CharField(max_length=32, unique=True)
    duration_days=models.DecimalField(max_digits=3, decimal_places=1)
    default_course_fee=models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    default_instructor_fee=models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    has_written_exam=models.BooleanField(default=False)
    has_online_exam=models.BooleanField(default=False)
    def __str__(self): return f"{self.name} ({self.code})"

class Instructor(models.Model):
    id=models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.PROTECT, related_name='instructor')
    name=models.CharField(max_length=255)
    address_line=models.CharField(max_length=255, blank=True)
    town=models.CharField(max_length=120, blank=True)
    postcode=models.CharField(max_length=12, blank=True)
    telephone=models.CharField(max_length=32, blank=True)
    email=models.EmailField(unique=True)
    bank_sort_code=models.CharField(max_length=16, blank=True)
    bank_account_number=models.CharField(max_length=20, blank=True)
    name_on_account=models.CharField(max_length=255, blank=True)
    def __str__(self): return self.name

class Booking(models.Model):
    id=models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business=models.ForeignKey(Business,on_delete=models.CASCADE,related_name='bookings')
    training_location=models.ForeignKey(TrainingLocation,on_delete=models.CASCADE,related_name='bookings')
    course_type=models.ForeignKey(CourseType,on_delete=models.CASCADE,related_name='bookings')
    instructor=models.ForeignKey(Instructor,on_delete=models.SET_NULL,null=True,blank=True,related_name='bookings')
    course_duration_days=models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    course_reference=models.CharField(max_length=64, unique=True)
    course_date=models.DateField()
    start_time=models.TimeField(default="09:30")
    course_fee=models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    instructor_fee=models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notes=models.TextField(blank=True)
    def __str__(self): return self.course_reference
class BookingDay(models.Model):
    id=models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking=models.ForeignKey(Booking,on_delete=models.CASCADE,related_name='days')
    day_no=models.PositiveIntegerField()
    day_date=models.DateField()
    start_time=models.TimeField()
    class Meta: unique_together=('booking','day_no')
    def __str__(self): return f"{self.booking.course_reference} - Day {self.day_no}"
class Attendance(models.Model):
    id=models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking_day=models.ForeignKey(BookingDay,on_delete=models.CASCADE,related_name='attendances')
    signed_at=models.DateTimeField(default=timezone.now)
    delegate_name=models.CharField(max_length=255)
    delegate_email=models.EmailField(blank=True)
    result=models.CharField(max_length=50, blank=True)
    notes=models.TextField(blank=True)
    def __str__(self): return f"{self.delegate_name} @ {self.booking_day}"


@receiver(post_save, sender=Business)
def sync_business_training_location(sender, instance: Business, created, **kwargs):
    """Keep a default TrainingLocation in sync with its Business when the
    'Add as training location' box is toggled."""
    if instance.add_as_training_location:
        qs = TrainingLocation.objects.filter(business=instance, name=instance.name).order_by('id')
        loc = qs.first()
        if not loc:
            loc = TrainingLocation(business=instance, name=instance.name)
        loc.address_line = instance.address_line
        loc.town = instance.town
        loc.postcode = instance.postcode
        loc.contact_name = instance.contact_name
        loc.telephone = instance.telephone
        loc.email = instance.email
        loc.save()
    else:
        TrainingLocation.objects.filter(business=instance, name=instance.name).delete()
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils.timezone import make_aware
from datetime import timedelta

from unicorn_project.training.models import FeedbackResponse, Booking



class Command(BaseCommand):
    help = "Safely attach existing feedback responses to matching bookings."

    def handle(self, *args, **options):
        updated = 0
        skipped = 0

        qs = FeedbackResponse.objects.filter(booking__isnull=True)

        self.stdout.write(f"Unlinked feedback rows found: {qs.count()}")

        for fb in qs:
            date_start = fb.date
            date_end = fb.date

            matches = Booking.objects.filter(
                course_type=fb.course_type,
                instructor=fb.instructor,
                course_date__gte=date_start - timedelta(days=1),
                course_date__lte=date_end + timedelta(days=1),
            ).order_by("course_date")

            booking = matches.first()

            if booking:
                fb.booking = booking
                fb.save(update_fields=["booking"])
                updated += 1
                self.stdout.write(
                    f"✅ Linked feedback {fb.id} → booking {booking.id}"
                )
            else:
                skipped += 1
                self.stdout.write(
                    f"⚠️  No booking match for feedback {fb.id} ({fb.course_type} / {fb.instructor} / {fb.date})"
                )

        self.stdout.write("-----")
        self.stdout.write(f"✅ Updated: {updated}")
        self.stdout.write(f"⚠️  Skipped (no safe match): {skipped}")

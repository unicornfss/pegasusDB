"""
Management command: retry_carry_forward

Re-runs the carry_forward_competencies logic for every DelegateRegister
whose booking_day is in the given booking (or all bookings if --all is given).

Usage:
    python manage.py retry_carry_forward --booking-id <pk>
    python manage.py retry_carry_forward --all
"""
from django.core.management.base import BaseCommand
from unicorn_project.training.models import Booking, DelegateRegister
from unicorn_project.training.services.carry_forward import carry_forward_competencies


class Command(BaseCommand):
    help = "Re-run carry_forward_competencies for delegates in a booking."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--booking-id", type=str, help="PK of the booking to process")
        group.add_argument("--all", action="store_true", help="Process every booking")

    def handle(self, *args, **options):
        if options["all"]:
            regs = DelegateRegister.objects.select_related(
                "booking_day__booking__course_type",
                "booking_day__booking__business",
            ).all()
        else:
            regs = DelegateRegister.objects.filter(
                booking_day__booking_id=options["booking_id"]
            ).select_related(
                "booking_day__booking__course_type",
                "booking_day__booking__business",
            )

        total = regs.count()
        self.stdout.write(f"Processing {total} register row(s)...")

        carried = 0
        for reg in regs:
            n = carry_forward_competencies(reg)
            if n:
                carried += n
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  ✓ {reg.name} (reg #{reg.pk}) — {n} competency/ies carried forward"
                    )
                )

        self.stdout.write(f"\nDone. {carried} competency/ies total carried forward across {total} registers.")

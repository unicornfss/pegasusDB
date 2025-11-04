from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from django.conf import settings
import os

from unicorn_project.training.models import AccidentReport


class Command(BaseCommand):
    help = "Anonymise injured fields after the following midnight, or all in test mode."

    def handle(self, *args, **options):
        today_local = timezone.localdate()
        now = timezone.now()

        # Check if in test mode
        test_mode = bool(
            getattr(settings, "ACCIDENT_ANON_TEST_MIN", None)
            or os.environ.get("ACCIDENT_ANON_TEST_MIN")
        )

        # Base queryset: not already anonymised and has data
        qs = AccidentReport.objects.filter(
            anonymized_at__isnull=True,
        ).filter(
            Q(injured_name__isnull=False) |
            Q(injured_address__isnull=False) |
            Q(first_aider_name__isnull=False) |
            Q(reporter_name__isnull=False)

        ).filter(
            Q(injured_name__gt="") |
            Q(injured_address__gt="") |
            Q(first_aider_name__gt="") |
            Q(reporter_name__gt="")
        )

        # Only apply the date rule in real mode
        if not test_mode:
            qs = qs.filter(date__lt=today_local)

        count = qs.update(
            injured_name="Anonymised",
            injured_address="Anonymised",
            first_aider_name="Anonymised",
            reporter_name = "Anonymised",
            anonymized_at=now,
        )

        mode = "TEST MODE" if test_mode else "Nightly mode"
        self.stdout.write(self.style.SUCCESS(
            f"[Anonymiser] ({mode}) Anonymised {count} report(s) at {now:%Y-%m-%d %H:%M:%S %Z}"
        ))

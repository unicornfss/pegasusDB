from django.core.management.base import BaseCommand

from unicorn_project.training.models import Personnel


class Command(BaseCommand):
    help = "Disable 2FA for all users with a stored TOTP secret"

    def handle(self, *args, **options):
        updated = Personnel.objects.exclude(totp_secret__isnull=True).exclude(totp_secret="").update(totp_secret=None)

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully disabled 2FA for {updated} user{'s' if updated != 1 else ''}."
            )
        )
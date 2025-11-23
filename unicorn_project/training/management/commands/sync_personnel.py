from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from unicorn_project.training.models import Personnel


class Command(BaseCommand):
    help = "Synchronise all User and Personnel records"

    def handle(self, *args, **options):
        self.stdout.write("Starting full sync...")

        for user in User.objects.filter(is_superuser=False):

            personnel, created = Personnel.objects.get_or_create(
                user=user,
                defaults={
                    "email": user.email,
                    "name": user.get_full_name() or user.username,
                }
            )

            # Ensure Personnel email matches User
            if personnel.email != user.email:
                personnel.email = user.email

            # Ensure Personnel has a name
            if not personnel.name.strip():
                personnel.name = user.get_full_name() or user.username

            # Split name into first / last
            parts = personnel.name.strip().split()
            if len(parts) == 1:
                first = parts[0]
                last = ""
            else:
                first = parts[0]
                last = " ".join(parts[1:])

            # Ensure User fields match
            if user.first_name != first or user.last_name != last:
                user.first_name = first
                user.last_name = last
                user.save(update_fields=["first_name", "last_name"])

            personnel.save()

            self.stdout.write(f"✔ Synced {user.username}")

        self.stdout.write(self.style.SUCCESS("All users synced!"))

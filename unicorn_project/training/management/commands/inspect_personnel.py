from django.core.management.base import BaseCommand, CommandError

from unicorn_project.training.models import Personnel


class Command(BaseCommand):
    help = "Inspect a Personnel record by email and show why it may be hidden or unusable"

    def add_arguments(self, parser):
        parser.add_argument("email", type=str, help="Personnel email address")

    def handle(self, *args, **options):
        email = (options["email"] or "").strip()
        personnel = Personnel.objects.select_related("user").filter(email__iexact=email).first()

        if not personnel:
            raise CommandError(f'No Personnel record found for "{email}".')

        user = personnel.user

        self.stdout.write(self.style.SUCCESS("Personnel record found"))
        self.stdout.write(f"id: {personnel.pk}")
        self.stdout.write(f"name: {personnel.name}")
        self.stdout.write(f"email: {personnel.email}")
        self.stdout.write(f"is_active: {personnel.is_active}")
        self.stdout.write(f"can_login: {personnel.can_login}")
        self.stdout.write(f"must_change_password: {personnel.must_change_password}")

        if not user:
            self.stdout.write(self.style.WARNING("linked user: none"))
            self.stdout.write("This record will block re-creation by email until you edit it or attach a user.")
            return

        self.stdout.write(f"linked user id: {user.pk}")
        self.stdout.write(f"linked username: {user.username}")
        self.stdout.write(f"linked user email: {user.email}")
        self.stdout.write(f"linked user active: {user.is_active}")
        self.stdout.write(f"linked user staff: {user.is_staff}")
        self.stdout.write(f"linked user superuser: {user.is_superuser}")

        if user.is_superuser:
            self.stdout.write(self.style.WARNING("This Personnel record is hidden from the custom personnel list for non-superusers."))

        if not personnel.is_active:
            self.stdout.write(self.style.WARNING("Personnel is archived (is_active=False)."))

        if not personnel.can_login:
            self.stdout.write(self.style.WARNING("Personnel login is disabled (can_login=False)."))
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Apply migrations and create the Postgres cache table (Render production helper)."

    def handle(self, *args, **options):
        call_command("migrate", "--noinput", verbosity=1)
        call_command("createcachetable", verbosity=1)
        self.stdout.write(self.style.SUCCESS("Deploy setup complete."))

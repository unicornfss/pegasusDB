from django.core.management.base import BaseCommand

from unicorn_project.training.utils.departure_reminders import send_due_departure_reminders


class Command(BaseCommand):
    help = "Send Telegram departure reminders for courses starting today."

    def handle(self, *args, **options):
        sent = send_due_departure_reminders()
        if sent:
            self.stdout.write(self.style.SUCCESS(f"Sent {sent} departure reminder(s)."))
        else:
            self.stdout.write("No departure reminders due.")

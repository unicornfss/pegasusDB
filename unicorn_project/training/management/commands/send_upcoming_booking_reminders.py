from django.core.management.base import BaseCommand

from unicorn_project.training.utils.upcoming_booking_reminders import send_due_upcoming_reminders


class Command(BaseCommand):
    help = "Send Telegram upcoming-booking reminders (days-before, at first-day start time)."

    def handle(self, *args, **options):
        sent = send_due_upcoming_reminders()
        if sent:
            self.stdout.write(self.style.SUCCESS(f"Sent {sent} upcoming booking reminder(s)."))
        else:
            self.stdout.write("No upcoming booking reminders due.")

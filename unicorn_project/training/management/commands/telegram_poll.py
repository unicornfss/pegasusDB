from django.core.management.base import BaseCommand

from unicorn_project.training.utils.telegram_bot import run_polling


class Command(BaseCommand):
    help = "Poll Telegram for bot commands (local development)."

    def handle(self, *args, **options):
        run_polling()

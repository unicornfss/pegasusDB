import logging

from django.core.management.base import BaseCommand

from unicorn_project.training.utils.telegram_bot import run_polling

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Poll Telegram for bot commands (local development)."

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.INFO)
        run_polling()

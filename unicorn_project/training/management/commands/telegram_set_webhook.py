import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand

from unicorn_project.training.utils.telegram_bot import clear_webhook, set_production_webhook


class Command(BaseCommand):
    help = "Register (or clear) the Telegram Bot API webhook for production."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Remove the webhook (use before local telegram_poll with the same bot).",
        )

    def handle(self, *args, **options):
        if not (settings.TELEGRAM_BOT_TOKEN or "").strip():
            self.stdout.write(
                self.style.WARNING("TELEGRAM_BOT_TOKEN is not set; skipping webhook setup.")
            )
            return

        if options["clear"]:
            asyncio.run(clear_webhook())
            self.stdout.write(self.style.SUCCESS("Telegram webhook cleared."))
            return

        if settings.DEBUG:
            self.stdout.write(
                "Skipping webhook registration in DEBUG mode (use telegram_poll locally)."
            )
            return

        if not (settings.TELEGRAM_WEBHOOK_SECRET or "").strip():
            self.stdout.write(
                self.style.WARNING("TELEGRAM_WEBHOOK_SECRET is not set; skipping webhook setup.")
            )
            return

        url = asyncio.run(set_production_webhook())
        self.stdout.write(self.style.SUCCESS(f"Telegram webhook registered: {url}"))

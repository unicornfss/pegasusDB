import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from telegram import Bot
from telegram.error import TelegramError


class Command(BaseCommand):
    help = "Check Telegram bot token, username, and whether polling/webhook is active."

    def handle(self, *args, **options):
        token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
        configured_username = (settings.TELEGRAM_BOT_USERNAME or "").strip().lstrip("@")

        if not token:
            self.stderr.write(self.style.ERROR("TELEGRAM_BOT_TOKEN is not set."))
            return

        bot = Bot(token)
        try:
            me = bot.get_me()
        except TelegramError as exc:
            self.stderr.write(self.style.ERROR(f"Token invalid or Telegram unreachable: {exc}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Bot OK: @{me.username} (id {me.id})"))
        if configured_username and configured_username.lower() != (me.username or "").lower():
            self.stderr.write(
                self.style.WARNING(
                    f"TELEGRAM_BOT_USERNAME is @{configured_username} but token belongs to @{me.username}."
                )
            )
        else:
            self.stdout.write(f"Configured username matches: @{me.username}")

        try:
            info = bot.get_webhook_info()
        except TelegramError as exc:
            self.stderr.write(self.style.ERROR(f"Could not read webhook info: {exc}"))
            return

        if info.url:
            self.stderr.write(
                self.style.WARNING(
                    f"Webhook is set to {info.url!r} — polling will not receive updates. "
                    "Run telegram_poll once to clear it, or deleteWebhook via Bot API."
                )
            )
        else:
            self.stdout.write("No webhook configured (polling mode OK).")

        self.stdout.write(
            "\nReminder: only ONE process may poll a bot token at a time.\n"
            "  Dev  → runserver + telegram_poll.bat (dev token only)\n"
            "  Live → Render unicorn-telegram-bot worker only (stop local poll)"
        )

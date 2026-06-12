import asyncio
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from telegram import Bot
from telegram.error import TelegramError


class Command(BaseCommand):
    help = "Check Telegram bot token, username, and whether polling/webhook is active."

    def handle(self, *args, **options):
        asyncio.run(self._check())

    async def _check(self):
        token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
        configured_username = (settings.TELEGRAM_BOT_USERNAME or "").strip().lstrip("@")

        if not token:
            self.stderr.write(self.style.ERROR("TELEGRAM_BOT_TOKEN is not set."))
            return

        bot = Bot(token)
        try:
            me = await bot.get_me()
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
            info = await bot.get_webhook_info()
        except TelegramError as exc:
            self.stderr.write(self.style.ERROR(f"Could not read webhook info: {exc}"))
            return

        if info.url:
            self.stdout.write(f"Webhook URL: {info.url}")
            self.stderr.write(
                self.style.WARNING(
                    "Webhook is active — polling (telegram_poll) will not receive updates. "
                    "Use telegram_set_webhook --clear before local polling."
                )
            )
        else:
            self.stdout.write("No webhook configured (polling mode OK for local dev).")

        self.stdout.write(
            "\nProduction: webhook on the web service (see telegram_set_webhook).\n"
            "Local dev: runserver + telegram_poll.bat with a separate dev bot."
        )

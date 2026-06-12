import logging

from django.conf import settings
from telegram.ext import Application, CommandHandler

from .telegram_handlers import bookings_command, directions_command, help_command, start_command

logger = logging.getLogger(__name__)


def build_application() -> Application:
    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("bookings", bookings_command))
    app.add_handler(CommandHandler("directions", directions_command))
    return app


def run_polling():
    logger.info("Starting Telegram bot polling…")
    build_application().run_polling(drop_pending_updates=True)

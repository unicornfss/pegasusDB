import logging
import sys

from django.conf import settings
from telegram.ext import Application, CommandHandler

from .telegram_handlers import bookings_command, directions_command, help_command, start_command

logger = logging.getLogger(__name__)


async def _on_startup(application: Application) -> None:
    me = await application.bot.get_me()
    configured = (settings.TELEGRAM_BOT_USERNAME or "").strip().lstrip("@")
    logger.info("Telegram bot ready: @%s (id %s)", me.username, me.id)
    if configured and configured.lower() != (me.username or "").lower():
        logger.error(
            "TELEGRAM_BOT_USERNAME=%r does not match token bot @%s — QR deep links will open the wrong chat.",
            configured,
            me.username,
        )


async def _on_error(update, context) -> None:
    logger.exception("Telegram handler error: %s", context.error)


def build_application() -> Application:
    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = Application.builder().token(token).post_init(_on_startup).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("bookings", bookings_command))
    app.add_handler(CommandHandler("directions", directions_command))
    app.add_error_handler(_on_error)
    return app


def run_polling():
    configured = (settings.TELEGRAM_BOT_USERNAME or "").strip().lstrip("@")
    logger.info("Starting Telegram bot polling (configured as @%s)…", configured or "?")
    print(
        f"Telegram polling starting for @{configured or '?'} — leave this terminal open. "
        "Only one poller may use each bot token.",
        flush=True,
    )
    try:
        build_application().run_polling(drop_pending_updates=True)
    except Exception as exc:
        msg = str(exc)
        if "Conflict" in msg or "getUpdates" in msg:
            print(
                "\nERROR: Another process is already polling this bot token (HTTP 409).\n"
                "  • Stop telegram_poll.bat elsewhere, or\n"
                "  • Remove this token from the Render worker if testing locally, or\n"
                "  • Use a separate dev bot token in .env (not the live production token).\n",
                file=sys.stderr,
                flush=True,
            )
        raise

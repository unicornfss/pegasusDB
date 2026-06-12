import logging

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone
from telegram import Update
from telegram.ext import ContextTypes

from ..models import Personnel
from .telegram_bookings import (
    booking_for_personnel_by_reference,
    format_bookings_list,
    format_directions_message,
    personnel_for_chat_id,
    upcoming_bookings_for_personnel,
)
from .telegram_link import consume_link_token

logger = logging.getLogger(__name__)


@sync_to_async
def _link_personnel(token, chat_id):
    personnel_id = consume_link_token(token)
    if not personnel_id:
        return None, (
            "That link is invalid or has expired. Open your Pegasus profile, "
            "refresh the page, and scan a new QR code."
        )

    try:
        personnel = Personnel.objects.get(pk=personnel_id, is_active=True)
    except Personnel.DoesNotExist:
        return None, "Could not find your Pegasus account for that link."

    existing = Personnel.objects.filter(telegram_chat_id=chat_id).exclude(pk=personnel.pk).first()
    if existing:
        return None, "This Telegram account is already linked to another Pegasus user."

    personnel.telegram_chat_id = str(chat_id)
    personnel.telegram_linked_at = timezone.now()
    personnel.notify_new_bookings_telegram = True
    personnel.notify_booking_changes_telegram = True
    personnel.notify_reminders_telegram = True
    personnel.save(
        update_fields=[
            "telegram_chat_id",
            "telegram_linked_at",
            "notify_new_bookings_telegram",
            "notify_booking_changes_telegram",
            "notify_reminders_telegram",
        ]
    )
    name = personnel.name or personnel.email
    return personnel, f"Linked to Pegasus as {name}. Use /bookings to see upcoming courses."


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return

    args = context.args or []
    if args:
        personnel, message = await _link_personnel(args[0], chat_id)
        await update.message.reply_text(message)
        return

    linked = await sync_to_async(personnel_for_chat_id)(str(chat_id))
    if linked:
        await update.message.reply_text(
            f"Already linked as {linked.name or linked.email}.\n"
            "Commands: /bookings · /directions REF · /help"
        )
        return

    bot = settings.TELEGRAM_BOT_USERNAME or "your_bot"
    await update.message.reply_text(
        f"Welcome to Unicorn Pegasus.\n\n"
        f"To link your account, open Profile in Pegasus and scan the Telegram QR code, "
        f"or open t.me/{bot} from the link shown there."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/start — link your Pegasus account (via profile QR)\n"
        "/bookings — list your upcoming bookings\n"
        "/directions REF — directions for a booking reference\n"
        "/help — this message"
    )


async def bookings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    personnel = await sync_to_async(personnel_for_chat_id)(chat_id)
    if not personnel:
        await update.message.reply_text("Account not linked. Use the QR code on your Pegasus profile.")
        return

    bookings = await sync_to_async(list)(upcoming_bookings_for_personnel(personnel))
    text = await sync_to_async(format_bookings_list)(bookings)
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def directions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    personnel = await sync_to_async(personnel_for_chat_id)(chat_id)
    if not personnel:
        await update.message.reply_text("Account not linked. Use the QR code on your Pegasus profile.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /directions COURSE-REF (example: /directions FA-ABC123)")
        return

    reference = context.args[0]
    booking = await sync_to_async(booking_for_personnel_by_reference)(personnel, reference)
    if not booking:
        await update.message.reply_text(f"No upcoming booking found with reference {reference}.")
        return

    text = await sync_to_async(format_directions_message)(booking)
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

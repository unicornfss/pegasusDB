import logging

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone
from telegram import Update
from telegram.ext import ContextTypes

from ..models import Personnel
from .telegram_bookings import (
    BOOKING_DETAIL_CALLBACK_PREFIX,
    booking_for_personnel_by_id,
    bookings_list_keyboard,
    format_booking_details_message,
    format_bookings_list,
    format_directions_message,
    next_upcoming_booking_for_personnel,
    personnel_for_chat_id,
    upcoming_bookings_for_personnel,
)
from .telegram_settings import (
    SETTINGS_CALLBACK_PREFIX,
    TELEGRAM_SETTING_KEYS,
    format_settings_message,
    settings_keyboard,
    toggle_personnel_setting,
)
from .telegram_today import (
    BOOKING_FEEDBACK_CALLBACK_PREFIX,
    BOOKING_REGISTER_CALLBACK_PREFIX,
    bookings_on_date_for_personnel,
    feedback_qr_photo_and_caption,
    format_today_message,
    registration_qr_photo_and_caption,
    telegram_qr_input_file,
    today_bookings_keyboard,
)

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
            "Commands: /today · /bookings · /directions · /settings · /help"
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
        "/today — today's course summary\n"
        "/bookings — list upcoming bookings (tap one or reply with its number)\n"
        "/directions — address and map link for your next booking\n"
        "/registration — registration QR and link for today's course\n"
        "/feedback — feedback QR and link for today's course\n"
        "/settings — turn booking alerts on or off\n"
        "/help — this message"
    )


def _store_bookings_pick_list(context, bookings):
    context.user_data["booking_ids"] = [b.pk for b in bookings]


async def _reply_booking_details(context, chat_id, booking):
    text = await sync_to_async(format_booking_details_message)(booking)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def bookings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    personnel = await sync_to_async(personnel_for_chat_id)(chat_id)
    if not personnel:
        await update.message.reply_text("Account not linked. Use the QR code on your Pegasus profile.")
        return

    bookings = await sync_to_async(list)(upcoming_bookings_for_personnel(personnel))
    _store_bookings_pick_list(context, bookings)
    text = await sync_to_async(format_bookings_list)(bookings)
    keyboard = bookings_list_keyboard(bookings) if bookings else None
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )


async def booking_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return

    data = query.data
    if not data.startswith(BOOKING_DETAIL_CALLBACK_PREFIX):
        await query.answer()
        return

    booking_id = data[len(BOOKING_DETAIL_CALLBACK_PREFIX):]
    if not booking_id:
        await query.answer("Could not read that booking.", show_alert=True)
        return

    await query.answer()

    try:
        personnel = await sync_to_async(personnel_for_chat_id)(str(chat_id))
        if not personnel:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Account not linked. Use the QR code on your Pegasus profile.",
            )
            return

        booking = await sync_to_async(booking_for_personnel_by_id)(personnel, booking_id)
        if not booking:
            await context.bot.send_message(
                chat_id=chat_id,
                text="That booking was not found or is no longer available.",
            )
            return

        await _reply_booking_details(context, chat_id, booking)
    except Exception:
        logger.exception("Telegram booking detail callback failed for %s", booking_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry, something went wrong loading that booking. Please try again.",
        )


async def booking_pick_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    booking_ids = context.user_data.get("booking_ids")
    if not booking_ids:
        return

    text = (update.message.text or "").strip()
    if not text.isdigit():
        return

    pick = int(text)
    if pick < 1 or pick > len(booking_ids):
        await update.message.reply_text(
            f"Please enter a number between 1 and {len(booking_ids)}, or run /bookings again."
        )
        return

    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    personnel = await sync_to_async(personnel_for_chat_id)(chat_id)
    if not personnel:
        await update.message.reply_text("Account not linked. Use the QR code on your Pegasus profile.")
        return

    booking = await sync_to_async(booking_for_personnel_by_id)(personnel, booking_ids[pick - 1])
    if not booking:
        await update.message.reply_text("That booking was not found or is no longer available.")
        return

    await _reply_booking_details(context, update.effective_chat.id, booking)


async def directions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id) if update.effective_chat else ""
    personnel = await sync_to_async(personnel_for_chat_id)(chat_id)
    if not personnel:
        await update.message.reply_text("Account not linked. Use the QR code on your Pegasus profile.")
        return

    booking = await sync_to_async(next_upcoming_booking_for_personnel)(personnel)
    text = await sync_to_async(format_directions_message)(booking)
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)


async def _linked_personnel_or_reply(update):
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return None, None
    personnel = await sync_to_async(personnel_for_chat_id)(str(chat_id))
    if not personnel:
        await update.effective_message.reply_text(
            "Account not linked. Use the QR code on your Pegasus profile."
        )
        return None, chat_id
    return personnel, chat_id


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    personnel, chat_id = await _linked_personnel_or_reply(update)
    if not personnel:
        return

    on_date = timezone.localdate()
    bookings = await sync_to_async(list)(bookings_on_date_for_personnel(personnel, on_date))
    text = await sync_to_async(format_today_message)(bookings, on_date)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    personnel, chat_id = await _linked_personnel_or_reply(update)
    if not personnel:
        return

    text = format_settings_message(personnel)
    keyboard = settings_keyboard(personnel)
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def settings_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if not data.startswith(SETTINGS_CALLBACK_PREFIX):
        await query.answer()
        return

    setting_key = data[len(SETTINGS_CALLBACK_PREFIX):]
    if setting_key not in TELEGRAM_SETTING_KEYS:
        await query.answer()
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return

    await query.answer()

    try:
        personnel = await sync_to_async(personnel_for_chat_id)(str(chat_id))
        if not personnel:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Account not linked. Use the QR code on your Pegasus profile.",
            )
            return

        personnel = await sync_to_async(toggle_personnel_setting)(personnel, setting_key)
        text = format_settings_message(personnel)
        keyboard = settings_keyboard(personnel)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception:
        logger.exception("Telegram settings toggle failed for key %s", setting_key)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry, something went wrong updating your settings. Please try again.",
        )


async def _send_today_form_qr(context, chat_id, booking, *, form_kind, on_date):
    if form_kind == "register":
        png, caption = await sync_to_async(registration_qr_photo_and_caption)(booking, on_date)
        filename = "register-qr.png"
    else:
        png, caption = await sync_to_async(feedback_qr_photo_and_caption)(booking, on_date)
        filename = "feedback-qr.png"

    if not png:
        await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")
        return

    await context.bot.send_photo(
        chat_id=chat_id,
        photo=telegram_qr_input_file(png, filename),
        caption=caption,
        parse_mode="HTML",
    )


async def _today_form_command(update, context, *, form_kind):
    personnel, chat_id = await _linked_personnel_or_reply(update)
    if not personnel:
        return

    on_date = timezone.localdate()
    bookings = await sync_to_async(list)(bookings_on_date_for_personnel(personnel, on_date))
    if not bookings:
        label = "registration" if form_kind == "register" else "feedback"
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"You have no courses scheduled for today, so there is no {label} form to share.",
        )
        return

    if len(bookings) == 1:
        await _send_today_form_qr(context, chat_id, bookings[0], form_kind=form_kind, on_date=on_date)
        return

    prefix = (
        BOOKING_REGISTER_CALLBACK_PREFIX
        if form_kind == "register"
        else BOOKING_FEEDBACK_CALLBACK_PREFIX
    )
    prompt = (
        "You have more than one course today. Select which registration form to share:"
        if form_kind == "register"
        else "You have more than one course today. Select which feedback form to share:"
    )
    keyboard = today_bookings_keyboard(bookings, on_date=on_date, callback_prefix=prefix)
    await context.bot.send_message(
        chat_id=chat_id,
        text=prompt,
        reply_markup=keyboard,
    )


async def registration_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _today_form_command(update, context, form_kind="register")


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _today_form_command(update, context, form_kind="feedback")


async def _today_form_callback(update, context, *, form_kind, callback_prefix):
    query = update.callback_query
    if not query or not query.data:
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    if not chat_id:
        return

    data = query.data
    if not data.startswith(callback_prefix):
        await query.answer()
        return

    booking_id = data[len(callback_prefix):]
    if not booking_id:
        await query.answer("Could not read that course.", show_alert=True)
        return

    await query.answer()

    try:
        personnel = await sync_to_async(personnel_for_chat_id)(str(chat_id))
        if not personnel:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Account not linked. Use the QR code on your Pegasus profile.",
            )
            return

        booking = await sync_to_async(booking_for_personnel_by_id)(personnel, booking_id)
        if not booking:
            await context.bot.send_message(
                chat_id=chat_id,
                text="That course was not found or is no longer available.",
            )
            return

        on_date = timezone.localdate()
        await _send_today_form_qr(context, chat_id, booking, form_kind=form_kind, on_date=on_date)
    except Exception:
        logger.exception("Telegram %s callback failed for %s", form_kind, booking_id)
        await context.bot.send_message(
            chat_id=chat_id,
            text="Sorry, something went wrong. Please try again.",
        )


async def booking_register_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _today_form_callback(
        update,
        context,
        form_kind="register",
        callback_prefix=BOOKING_REGISTER_CALLBACK_PREFIX,
    )


async def booking_feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _today_form_callback(
        update,
        context,
        form_kind="feedback",
        callback_prefix=BOOKING_FEEDBACK_CALLBACK_PREFIX,
    )

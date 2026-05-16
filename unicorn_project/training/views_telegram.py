import json
import logging
import secrets
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.conf import settings
from telegram import Bot, Update
from telegram.error import TelegramError
from .models import Personnel
import qrcode
import io
import base64
from django.contrib.auth.decorators import login_required

logger = logging.getLogger(__name__)
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

@csrf_exempt
@require_POST
def telegram_webhook(request):
    try:
        update = Update.de_json(json.loads(request.body), bot)
    except Exception as e:
        logger.error(f"Failed to parse Telegram update: {e}")
        return HttpResponseBadRequest("Invalid update")

    message = update.message
    if not message:
        return JsonResponse({"ok": True})

    chat_id = message.chat.id
    username = message.from_user.username or ""
    text = message.text or ""

    if text.strip().lower().startswith("/start"):
        parts = text.strip().split()
        token = parts[1] if len(parts) > 1 else None

        if token:
            try:
                personnel = Personnel.objects.get(telegram_link_token=token)
                personnel.telegram_chat_id = str(chat_id)
                personnel.telegram_username = username
                personnel.telegram_link_token = None  # Clear token after linking
                personnel.save(update_fields=["telegram_chat_id", "telegram_username", "telegram_link_token"])
                logger.info(f"Linked Telegram chat ID {chat_id} to user with token {token}")
                bot.send_message(chat_id=chat_id, text="Your Telegram account has been linked successfully.")
            except Personnel.DoesNotExist:
                logger.warning(f"Invalid Telegram link token received: {token}")
                bot.send_message(chat_id=chat_id, text="Invalid or expired link token. Please try linking again from your profile.")
            except Exception as e:
                logger.error(f"Error linking Telegram chat ID: {e}")
                bot.send_message(chat_id=chat_id, text="An error occurred while linking your account. Please contact support.")
        else:
            bot.send_message(chat_id=chat_id, text="Please send the link token after /start command. You can find it in your profile page.")
    else:
        # Handle other messages or ignore
        pass

    return JsonResponse({"ok": True})

@login_required
def telegram_link_token(request):
    personnel = request.user.personnel
    if not personnel.telegram_link_token:
        personnel.telegram_link_token = secrets.token_urlsafe(32)
        personnel.save(update_fields=["telegram_link_token"])

    # Generate a Telegram deep link with the token
    bot_username = "YourBotUsername"  # Replace with your actual bot username
    deep_link = f"https://t.me/{bot_username}?start={personnel.telegram_link_token}"

    # Generate QR code image
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(deep_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    qr_code_url = f"data:image/png;base64,{img_str}"

    return JsonResponse({"qr_code_url": qr_code_url})
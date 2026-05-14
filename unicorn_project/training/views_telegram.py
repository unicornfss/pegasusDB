import json
import logging
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.conf import settings
from telegram import Bot, Update
from telegram.error import TelegramError
from .models import Personnel

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

    if text.strip().lower() == "/start":
        # Link the chat ID to the Personnel record by username
        try:
            personnel = Personnel.objects.get(telegram_username__iexact=username)
            personnel.telegram_chat_id = str(chat_id)
            personnel.save(update_fields=["telegram_chat_id"])
            logger.info(f"Linked Telegram chat ID {chat_id} to user {username}")
        except Personnel.DoesNotExist:
            logger.warning(f"Telegram username {username} not found in Personnel")
        except Exception as e:
            logger.error(f"Error linking Telegram chat ID: {e}")

        # Optionally send a welcome message
        try:
            bot.send_message(chat_id=chat_id, text="Your Telegram account has been linked successfully.")
        except TelegramError as e:
            logger.error(f"Failed to send welcome message: {e}")

    return JsonResponse({"ok": True})
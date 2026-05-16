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

logger = logging.getLogger(__name__)
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
import qrcode
import io
import base64

@login_required
def telegram_link_token(request):
    personnel = request.user.personnel
    if not personnel.telegram_link_token:
        import secrets
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

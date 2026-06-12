import base64
import io

import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .models import Personnel
from .utils.telegram_link import create_link_token


@login_required
def telegram_link_token(request):
    try:
        personnel = request.user.personnel
    except Personnel.DoesNotExist:
        return JsonResponse({"error": "No personnel profile."}, status=400)

    bot_username = (settings.TELEGRAM_BOT_USERNAME or "").strip().lstrip("@")
    if not bot_username:
        return JsonResponse({"error": "TELEGRAM_BOT_USERNAME is not configured."}, status=503)

    token = create_link_token(personnel.pk)
    deep_link = f"https://t.me/{bot_username}?start={token}"

    qr = qrcode.make(deep_link)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    qr_data_url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    return JsonResponse(
        {
            "deep_link": deep_link,
            "qr_data_url": qr_data_url,
            "linked": bool((personnel.telegram_chat_id or "").strip()),
            "linked_at": personnel.telegram_linked_at.isoformat() if personnel.telegram_linked_at else None,
        }
    )


@login_required
@require_POST
def telegram_unlink(request):
    try:
        personnel = request.user.personnel
    except Personnel.DoesNotExist:
        return redirect("user_profile")

    personnel.telegram_chat_id = ""
    personnel.telegram_linked_at = None
    personnel.save(update_fields=["telegram_chat_id", "telegram_linked_at"])
    messages.success(request, "Telegram account unlinked.")
    return redirect("user_profile")

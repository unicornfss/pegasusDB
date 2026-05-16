"""
Telegram account linking and management views.
"""
import logging
import uuid
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.contrib import messages
from django.core.cache import cache

from .models import TelegramAccount, Personnel
from .telegram_bot import get_telegram_service
from .qr_code_utils import generate_telegram_qr_code_base64

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def telegram_link_account(request):
    """
    Display QR code for linking Telegram account or unlink button if already linked.
    """
    try:
        personnel = request.user.personnel
    except Personnel.DoesNotExist:
        messages.error(request, "Your user account is not linked to a Personnel record.")
        return redirect('dashboard')  # Adjust to your dashboard URL

    telegram_account = getattr(personnel, 'telegram_account', None)

    if telegram_account:
        # Already linked - show unlink button
        context = {
            'linked': True,
            'telegram_account': telegram_account,
        }
        return render(request, 'telegram_link_account.html', context)
    
    # Not linked yet - generate QR code
    linking_token = str(uuid.uuid4())
    
    # Store the linking token in cache with personnel ID
    cache_key = f"telegram_linking_{linking_token}"
    cache.set(cache_key, {
        'personnel_id': str(personnel.id),
        'created_at': __import__('django.utils.timezone', fromlist=['now']).now(),
    }, timeout=3600)  # 1 hour expiration
    
    bot_service = get_telegram_service()
    deep_link = bot_service.create_linking_qr_code(linking_token)
    qr_code_base64 = generate_telegram_qr_code_base64(deep_link)
    
    context = {
        'linked': False,
        'qr_code_base64': qr_code_base64,
        'deep_link': deep_link,
        'linking_token': linking_token,
    }
    
    return render(request, 'telegram_link_account.html', context)


@login_required
@require_http_methods(["POST"])
def telegram_unlink_account(request):
    """
    Unlink the user's Telegram account.
    """
    try:
        personnel = request.user.personnel
        telegram_account = personnel.telegram_account
        telegram_account.delete()
        messages.success(request, "Your Telegram account has been unlinked.")
    except (Personnel.DoesNotExist, TelegramAccount.DoesNotExist):
        messages.error(request, "No Telegram account to unlink.")
    except Exception as e:
        logger.error(f"Error unlinking Telegram account: {e}")
        messages.error(request, "An error occurred while unlinking your account.")
    
    return redirect('telegram_link_account')  # Adjust to your view name


@csrf_exempt
@require_http_methods(["POST"])
def telegram_webhook(request):
    """
    Webhook endpoint for Telegram bot updates.
    Handles /start command and processes account linking.
    """
    import json
    
    try:
        data = json.loads(request.body)
        update_id = data.get('update_id')
        message = data.get('message', {})
        
        if not message:
            return JsonResponse({'ok': True})
        
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '').strip()
        from_user = message.get('from', {})
        telegram_id = from_user.get('id')
        
        # Handle /start command with linking token
        if text.startswith('/start'):
            parts = text.split()
            if len(parts) > 1:
                linking_token = parts[1]
                handle_telegram_linking(telegram_id, from_user, linking_token)
        
        return JsonResponse({'ok': True})
    
    except json.JSONDecodeError:
        logger.error("Invalid JSON received in webhook")
        return JsonResponse({'ok': False}, status=400)
    except Exception as e:
        logger.error(f"Error processing Telegram webhook: {e}")
        return JsonResponse({'ok': False}, status=500)


def handle_telegram_linking(telegram_id: int, from_user: dict, linking_token: str):
    """
    Process linking a Telegram account to a Personnel account.
    
    Args:
        telegram_id: Telegram user ID
        from_user: User data from Telegram (contains username, first_name, last_name)
        linking_token: The linking token generated earlier
    """
    from django.core.cache import cache
    
    try:
        cache_key = f"telegram_linking_{linking_token}"
        linking_data = cache.get(cache_key)
        
        if not linking_data:
            logger.warning(f"Invalid or expired linking token: {linking_token}")
            return False
        
        personnel_id = linking_data.get('personnel_id')
        personnel = Personnel.objects.get(id=personnel_id)
        
        # Check if this Telegram ID is already linked to someone else
        existing = TelegramAccount.objects.filter(telegram_id=telegram_id).exclude(
            personnel_id=personnel_id
        ).first()
        if existing:
            logger.warning(f"Telegram ID {telegram_id} already linked to another account")
            return False
        
        # Create or update TelegramAccount
        telegram_account, created = TelegramAccount.objects.update_or_create(
            personnel=personnel,
            defaults={
                'telegram_id': telegram_id,
                'telegram_username': from_user.get('username', ''),
                'first_name': from_user.get('first_name', ''),
                'last_name': from_user.get('last_name', ''),
            }
        )
        
        # Clear the linking token
        cache.delete(cache_key)
        
        logger.info(f"Successfully linked Personnel {personnel_id} to Telegram {telegram_id}")
        return True
    
    except Personnel.DoesNotExist:
        logger.error(f"Personnel not found for linking token {linking_token}")
        return False
    except Exception as e:
        logger.error(f"Error handling Telegram linking: {e}")
        return False

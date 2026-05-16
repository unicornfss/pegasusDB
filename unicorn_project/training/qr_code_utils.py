"""
QR code generation utilities for Telegram linking.
"""
import io
import qrcode
from django.core.files.base import ContentFile


def generate_telegram_qr_code(deep_link_url: str) -> bytes:
    """
    Generate a QR code for a Telegram deep link.
    
    Args:
        deep_link_url: The Telegram deep link URL (e.g., https://t.me/bot?start=token)
        
    Returns:
        QR code image as PNG bytes
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=2,
    )
    qr.add_data(deep_link_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert PIL Image to bytes
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return buffer.getvalue()


def generate_telegram_qr_code_base64(deep_link_url: str) -> str:
    """
    Generate a QR code and return as base64 string for embedding in HTML.
    
    Args:
        deep_link_url: The Telegram deep link URL
        
    Returns:
        Base64 encoded PNG image string
    """
    import base64
    qr_bytes = generate_telegram_qr_code(deep_link_url)
    return base64.b64encode(qr_bytes).decode('utf-8')

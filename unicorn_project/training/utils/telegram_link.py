import hashlib
import hmac
import logging
import time
import uuid

from django.conf import settings

logger = logging.getLogger(__name__)

LINK_TTL_SECONDS = 3600


def _link_secret() -> bytes:
    return f"{settings.SECRET_KEY}:telegram-link-v1".encode()


def _personnel_uuid_hex(personnel_id) -> str:
    return uuid.UUID(str(personnel_id)).hex


def create_link_token(personnel_id) -> str:
    """
    Build a Telegram /start payload (max 64 chars, A–Z a–z 0–9 _ - only).
    Signed with SECRET_KEY so web and telegram_poll worker do not need a shared cache.
    """
    pid_hex = _personnel_uuid_hex(personnel_id)
    issued_at = int(time.time())
    payload = f"{pid_hex}.{issued_at}".encode()
    digest = hmac.new(_link_secret(), payload, hashlib.sha256).hexdigest()[:12]
    return f"{pid_hex}-{issued_at}-{digest}"


def consume_link_token(token: str):
    token = (token or "").strip()
    parts = token.split("-")
    if len(parts) != 3:
        logger.warning("Telegram link rejected: expected 3 token parts, got %s", len(parts))
        return None

    pid_hex, issued_at_str, digest = parts
    if len(pid_hex) != 32 or len(digest) != 12:
        logger.warning("Telegram link rejected: malformed token segments")
        return None

    try:
        issued_at = int(issued_at_str)
    except ValueError:
        logger.warning("Telegram link rejected: invalid timestamp")
        return None

    age = time.time() - issued_at
    if age < 0 or age > LINK_TTL_SECONDS:
        logger.warning("Telegram link rejected: token age %ss (ttl %ss)", int(age), LINK_TTL_SECONDS)
        return None

    payload = f"{pid_hex}.{issued_at}".encode()
    expected = hmac.new(_link_secret(), payload, hashlib.sha256).hexdigest()[:12]
    if not hmac.compare_digest(digest, expected):
        logger.warning(
            "Telegram link rejected: HMAC mismatch — token was not signed with this "
            "server's DJANGO_SECRET_KEY (often caused by local telegram_poll using the "
            "production bot token, or web/worker secret mismatch on Render)."
        )
        return None

    try:
        return str(uuid.UUID(hex=pid_hex))
    except ValueError:
        logger.warning("Telegram link rejected: invalid personnel UUID")
        return None

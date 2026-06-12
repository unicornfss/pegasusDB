import secrets

from django.core.cache import cache

LINK_CACHE_PREFIX = "telegram_link:"
LINK_TTL_SECONDS = 3600


def create_link_token(personnel_id) -> str:
    token = secrets.token_urlsafe(24)
    cache.set(f"{LINK_CACHE_PREFIX}{token}", str(personnel_id), timeout=LINK_TTL_SECONDS)
    return token


def consume_link_token(token: str):
    if not token:
        return None
    key = f"{LINK_CACHE_PREFIX}{token.strip()}"
    personnel_id = cache.get(key)
    if personnel_id:
        cache.delete(key)
    return personnel_id

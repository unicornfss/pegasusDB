from django.conf import settings


def public_site_url() -> str:
    """Base URL for links opened on phones and other off-machine clients."""
    return (
        getattr(settings, "PUBLIC_SITE_URL", None)
        or getattr(settings, "SITE_URL", "")
        or ""
    ).rstrip("/")

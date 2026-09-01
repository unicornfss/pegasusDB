"""Helpers for business portal login emails and magic links."""
from __future__ import annotations

from django.core import signing
from django.db.models import Q

from ..models import Business, BusinessPortalEmail

SIGNING_SALT = "business-portal-login-v1"
TOKEN_MAX_AGE = 60 * 60  # 1 hour


def normalise_email(email: str | None) -> str:
    return (email or "").strip().lower()


def businesses_for_portal_email(email: str):
    """Businesses this email may access (primary email or portal allowlist)."""
    email = normalise_email(email)
    if not email:
        return Business.objects.none()
    return (
        Business.objects.filter(
            Q(email__iexact=email) | Q(portal_emails__email__iexact=email)
        )
        .distinct()
        .order_by("name")
    )


def email_can_access_business(email: str, business: Business) -> bool:
    email = normalise_email(email)
    if not email or not business:
        return False
    primary = normalise_email(business.email)
    if primary and primary == email:
        return True
    return business.portal_emails.filter(email__iexact=email).exists()


def add_portal_email(business: Business, email: str) -> BusinessPortalEmail | None:
    """
    Ensure email is on the business portal allowlist.
    Skips blanks and emails that already match the primary business email.
    """
    email = normalise_email(email)
    if not email or not business or not business.pk:
        return None
    if normalise_email(business.email) == email:
        return None
    obj, _created = BusinessPortalEmail.objects.get_or_create(
        business=business,
        email=email,
    )
    return obj


def sync_portal_emails_from_text(business: Business, raw: str) -> None:
    """
    Replace additional portal emails with the addresses listed in `raw`
    (one per line or comma-separated). Primary business.email is never stored here.
    """
    if not business or not business.pk:
        return
    primary = normalise_email(business.email)
    wanted = set()
    for part in (raw or "").replace(",", "\n").splitlines():
        e = normalise_email(part)
        if e and e != primary:
            wanted.add(e)

    existing = {normalise_email(x.email): x for x in business.portal_emails.all()}
    for e, row in existing.items():
        if e not in wanted:
            row.delete()
    for e in wanted:
        if e not in existing:
            BusinessPortalEmail.objects.create(business=business, email=e)


def create_login_token(email: str) -> str:
    return signing.dumps({"email": normalise_email(email)}, salt=SIGNING_SALT)


def consume_login_token(token: str) -> str | None:
    try:
        data = signing.loads(token, salt=SIGNING_SALT, max_age=TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    except signing.SignatureExpired:
        return None
    email = normalise_email(data.get("email") if isinstance(data, dict) else "")
    return email or None

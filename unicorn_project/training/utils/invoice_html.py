from __future__ import annotations
from django.conf import settings
from django.template.loader import render_to_string

# WeasyPrint is optional at import time so your server still boots even if it's missing.
try:
    from weasyprint import HTML  # type: ignore
except Exception:  # pragma: no cover
    HTML = None  # type: ignore

DEFAULT_ADMIN_EMAIL_DEV = "jon.ostrowski@hotmail.com"
DEFAULT_ADMIN_EMAIL_PROD = "info@unicornsafety.co.uk"

def render_invoice_pdf_from_html(template_name: str, context: dict) -> tuple[bytes, str, str]:
    """
    Render an HTML template to PDF using WeasyPrint (if available).
    Falls back to returning HTML bytes if WeasyPrint isn't installed.
    Returns: (file_bytes, filename, content_type)
    """
    html_str = render_to_string(template_name, context)
    filename = f"invoice-{context.get('course_ref','invoice')}.pdf"

    if HTML is None:
        # Fallback: return HTML so the user gets a file anyway (good for dev if WeasyPrint missing)
        return html_str.encode("utf-8"), filename.replace(".pdf", ".html"), "text/html; charset=utf-8"

    pdf_bytes = HTML(string=html_str, base_url=getattr(settings, "BASE_DIR", None)).write_pdf()
    return pdf_bytes, filename, "application/pdf"

def resolve_admin_email() -> str:
    """
    In dev send everything to Jon; in prod to info@...
    - DEV/DEBUG True -> dev email
    - Otherwise ADMIN_EMAIL if set -> else prod default
    """
    if getattr(settings, "DEBUG", False):
        return getattr(settings, "ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL_DEV) or DEFAULT_ADMIN_EMAIL_DEV
    return getattr(settings, "ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL_PROD) or DEFAULT_ADMIN_EMAIL_PROD

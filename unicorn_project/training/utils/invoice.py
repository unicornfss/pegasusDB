
"""
Invoice utilities for Unicorn project.

Drop this file at:
  unicorn_project/training/utils/invoice.py

Provides (backwards compatible):
  - get_invoice_template_path()
  - render_invoice_file(context, prefer_pdf=True) -> (bytes, filename)
  - render_invoice_pdf(context) -> (bytes, filename)  # wrapper
  - send_invoice_email(pdf_or_docx_bytes, filename, subject, body, *, to_admin=True, cc_instructor=None)
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Dict, Tuple, Optional

from django.conf import settings
from django.core.mail import EmailMessage
from django.template import engines

# Third-party
from docxtpl import DocxTemplate

# docx2pdf is optional (e.g., CI/Linux without Word). We fall back to DOCX.
try:
    from docx2pdf import convert as docx2pdf_convert
    _DOCX2PDF_AVAILABLE = True
except Exception:
    _DOCX2PDF_AVAILABLE = False


# ------------------------------
# Template resolution
# ------------------------------
def get_invoice_template_path() -> Path:
    """
    Resolve the path to templates/invoicing/Invoice.docx.
    Checks project-level templates dir first, then app-level.
    Raises FileNotFoundError if not found.
    """
    candidates = []

    # 1) Project-level templates/<...>
    base_dirs = []
    # Collect DIRS from TEMPLATES setting
    try:
        for eng in settings.TEMPLATES:
            for d in eng.get("DIRS", []) or []:
                base_dirs.append(Path(d))
    except Exception:
        pass

    # Also try manage.py project root
    base_dirs.append(Path(settings.BASE_DIR) / "templates")

    for root in base_dirs:
        candidates.append(Path(root) / "invoicing" / "Invoice.docx")

    # 2) App-level default
    app_level = Path(settings.BASE_DIR) / "unicorn_project" / "training" / "templates" / "invoicing" / "Invoice.docx"
    candidates.append(app_level)

    for p in candidates:
        if p.exists():
            return p

    # Not found -> raise helpful error
    raise FileNotFoundError(
        "Invoice.docx template not found. Looked in:\n" + "\n".join(str(p) for p in candidates)
    )


# ------------------------------
# Renderers
# ------------------------------
def _render_docx_bytes(context: Dict) -> bytes:
    """Render the DOCX template with docxtpl and return DOCX bytes."""
    tpl_path = get_invoice_template_path()
    doc = DocxTemplate(str(tpl_path))
    # docxtpl uses jinja2 internally; context keys must match placeholders.
    doc.render(context or {})
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _try_convert_docx_to_pdf(docx_bytes: bytes) -> Optional[bytes]:
    """Try to convert DOCX bytes to PDF bytes using docx2pdf (Windows/Word)."""
    if not _DOCX2PDF_AVAILABLE:
        return None
    # Write to a temp DOCX, convert to PDF temp, then read back.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        in_path = td_path / "invoice.docx"
        out_path = td_path / "invoice.pdf"
        in_path.write_bytes(docx_bytes)
        try:
            # On Windows, docx2pdf calls Word; must run in real filesystem.
            docx2pdf_convert(str(in_path), str(out_path))
        except Exception:
            return None
        if out_path.exists():
            return out_path.read_bytes()
        return None


def render_invoice_file(context: Dict, prefer_pdf: bool = True) -> Tuple[bytes, str]:
    """
    Render the invoice using the DOCX template.
    If prefer_pdf and conversion works, returns (pdf_bytes, 'invoice.pdf').
    Otherwise returns (docx_bytes, 'invoice.docx').
    """
    docx_bytes = _render_docx_bytes(context)
    if prefer_pdf:
        pdf_bytes = _try_convert_docx_to_pdf(docx_bytes)
        if pdf_bytes:
            return pdf_bytes, "invoice.pdf"
    return docx_bytes, "invoice.docx"


# Backwards compatible wrapper some views imported earlier
def render_invoice_pdf(context: Dict) -> Tuple[bytes, str]:
    """
    Render and *attempt* to return PDF; fallback to DOCX.
    """
    return render_invoice_file(context, prefer_pdf=True)


# ------------------------------
# Email helper
# ------------------------------
def _get_admin_email() -> str:
    """
    Always return the real admin inbox (prod target).
    Redirection to the dev catch-all happens in send_invoice_email().
    """
    return getattr(settings, "ADMIN_INBOX_EMAIL", None) or "info@unicornsafety.co.uk"


def send_invoice_email(
    file_bytes: bytes,
    filename: str,
    subject: str,
    body: str,
    *,
    to_admin: bool = True,
    cc_instructor: Optional[str] = None,
) -> None:
    """
    Send the rendered invoice to admin (and optionally CC instructor).

    In development you can set:
      settings.DEV_EMAIL_ROUTING = "jon.ostrowski@hotmail.com"
    to force all admin mail there.
    """
    to_addr = [_get_admin_email()] if to_admin else []
    if not to_addr:
        raise RuntimeError("No admin email configured.")

    # If a dev catch-all is set, redirect ALL recipients there (no real CC)
    catch_all = getattr(settings, "DEV_CATCH_ALL_EMAIL", "") or os.environ.get("DEV_CATCH_ALL_EMAIL", "")
    if catch_all:
        original = ", ".join([a for a in to_addr if a] + ([cc_instructor] if cc_instructor else [])) or "(none)"
        subject = f"[DEV → {original}] {subject}"
        body = (
            "This message was redirected to the dev catch-all mailbox.\n"
            f"Original recipients: {original}\n\n"
        ) + (body or "")
        to_addr = [catch_all]
        cc_list = None
    else:
        cc_list = [cc_instructor] if cc_instructor else None

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@unicornsafety.co.uk"),
        to=to_addr,
        cc=cc_list,
    )

    email.attach(filename, file_bytes)
    email.send(fail_silently=False)

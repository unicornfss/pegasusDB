import os, base64, requests, os.path as _path
from typing import Iterable, Tuple, Optional, Union
from django.conf import settings

Attachment = Union[str, Tuple[str, Union[bytes, str], str]]  # path OR (filename, content, mimetype)

def _split_from(df: str) -> tuple[str, str]:
    if "<" in df and ">" in df:
        name = df.split("<", 1)[0].strip().strip('"')
        email = df.split("<", 1)[1].split(">", 1)[0].strip()
        return name, email
    return "", df.strip()

def _dest() -> str:
    return settings.DEV_CATCH_ALL_EMAIL if getattr(settings, "DEBUG", False) else settings.ADMIN_INBOX_EMAIL

def _attachments_payload(attachments: Iterable[Attachment] | None):
    out = []
    for a in attachments or []:
        if isinstance(a, str):
            with open(a, "rb") as f:
                content = f.read()
            filename = _path.basename(a)
            mimetype = "application/octet-stream"
        else:
            filename, content, mimetype = a
            if isinstance(content, str):
                content = content.encode("utf-8")
        out.append({
            "filename": filename,
            "content": base64.b64encode(content).decode("ascii"),
            "type": mimetype,
            "disposition": "attachment",
        })
    return out

def send_admin_email(
    subject: str,
    body: str,
    attachments: Optional[Iterable[Attachment]] = None,
    reply_to: Optional[Iterable[str]] = None,
    html: bool = False,
) -> int:
    # Read provider + keys from Django settings first, falling back to env.
    provider = getattr(settings, "EMAIL_PROVIDER", os.getenv("EMAIL_PROVIDER", "mailersend")).lower()
    from_name, from_email = _split_from(getattr(settings, "DEFAULT_FROM_EMAIL", ""))
    if not from_email:
        raise RuntimeError("DEFAULT_FROM_EMAIL missing")
    to_addr = _dest()
    if not to_addr:
        raise RuntimeError("Destination email missing (DEV_CATCH_ALL_EMAIL/ADMIN_INBOX_EMAIL)")

    att = _attachments_payload(attachments)
    text_part = None if html else body
    html_part = body if html else None

    if provider == "resend":
        api_key = getattr(settings, "RESEND_API_KEY", os.getenv("RESEND_API_KEY"))
        if not api_key:
            raise RuntimeError("RESEND_API_KEY missing")
        payload = {
            "from": f"{from_name} <{from_email}>" if from_name else from_email,
            "to": [to_addr],
            "subject": subject,
            "text": text_part,
            "html": html_part,
            "attachments": [{"filename": a["filename"], "content": a["content"]} for a in att],
            "reply_to": reply_to[0] if reply_to else None,
        }
        r = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=30,
        )

    elif provider == "smtp2go":
        api_key = getattr(settings, "SMTP2GO_API_KEY", os.getenv("SMTP2GO_API_KEY"))
        if not api_key:
            raise RuntimeError("SMTP2GO_API_KEY missing")
        s2go_atts = [{"filename": a["filename"], "file_blob": a["content"], "mime_type": a["type"]} for a in att]
        payload = {
            "sender": from_email if not from_name else f"{from_name} <{from_email}>",
            "to": [to_addr],
            "subject": subject,
            "text_body": text_part or "",
            "html_body": html_part or None,
            "attachments": s2go_atts or None,
            "reply_to": reply_to[0] if reply_to else None,
        }
        r = requests.post(
            "https://api.smtp2go.com/v3/email/send",
            headers={"Content-Type": "application/json", "X-Smtp2go-Api-Key": api_key},
            json=payload, timeout=30,
        )

    else:  # mailersend
        api_key = getattr(settings, "MAILERSEND_API_KEY", os.getenv("MAILERSEND_API_KEY"))
        if not api_key:
            raise RuntimeError("MAILERSEND_API_KEY missing")
        payload = {
            "from": {"email": from_email, "name": from_name or None},
            "to": [{"email": to_addr}],
            "subject": subject,
            "text": text_part,
            "html": html_part,
            "attachments": att,
        }
        if reply_to:
            payload["reply_to"] = [{"email": reply_to[0]}]
        r = requests.post(
            "https://api.mailersend.com/v1/email",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=30,
        )

    # Uniform error surface with correct provider name
    if r.status_code >= 400:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise RuntimeError(f"{provider} API {r.status_code}: {detail}")
    return 1

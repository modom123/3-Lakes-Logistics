"""Email via Resend → Postmark → stdout fallback (step 90)."""
from __future__ import annotations

import httpx

from ..logging_service import get_logger
from ..settings import get_settings

_log = get_logger("3ll.email")


def send_email(to: str, subject: str, html: str, *, tag: str | None = None) -> dict:
    s = get_settings()
    if s.resend_api_key:
        return _via_resend(to, subject, html, tag, s)
    if s.postmark_server_token:
        return _via_postmark(to, subject, html, tag, s)
    _log.info("EMAIL[dev] to=%s subject=%s", to, subject)
    return {"status": "stub", "reason": "no_provider_configured"}


def _via_resend(to, subject, html, tag, s):
    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {s.resend_api_key}"},
            json={
                "from": s.postmark_from_email, "to": to,
                "subject": subject, "html": html,
                "tags": [{"name": "kind", "value": tag}] if tag else [],
            },
            timeout=15,
        )
        r.raise_for_status()
        return {"status": "sent", "provider": "resend", "id": r.json().get("id")}
    except Exception as exc:  # noqa: BLE001
        _log.exception("resend failed")
        return {"status": "error", "error": str(exc)}


def _via_postmark(to, subject, html, tag, s):
    try:
        r = httpx.post(
            "https://api.postmarkapp.com/email",
            headers={"X-Postmark-Server-Token": s.postmark_server_token,
                     "Accept": "application/json"},
            json={"From": s.postmark_from_email, "To": to,
                  "Subject": subject, "HtmlBody": html, "Tag": tag},
            timeout=15,
        )
        r.raise_for_status()
        return {"status": "sent", "provider": "postmark", "id": r.json().get("MessageID")}
    except Exception as exc:  # noqa: BLE001
        _log.exception("postmark failed")
        return {"status": "error", "error": str(exc)}

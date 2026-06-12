"""SMTP email sending via Hostinger — for compose/reply from Eagle Eye.

Transactional emails (settlement, welcome, dispatch) continue to use Postmark.
Manual compose/reply from the Email Center uses this module to send directly
from the appropriate Hostinger mailbox account.

Hostinger SMTP: smtp.hostinger.com:465 (SSL)
"""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..settings import get_settings
from ..supabase_client import get_supabase

log = logging.getLogger("3ll.email.smtp")

SMTP_HOST = "smtp.hostinger.com"
SMTP_PORT = 465

MAILBOX_ADDRESSES: dict[str, str] = {
    "loads": "loads@3lakeslogistics.com",
    "sales": "sales@3lakeslogistics.com",
    "info":  "info@3lakeslogistics.com",
    "mark":  "mark@3lakeslogistics.com",
    "cece":  "cece@3lakeslogistics.com",
}


def send_from_mailbox(
    mailbox: str,
    to: list[str],
    subject: str,
    body_html: str = "",
    body_text: str = "",
    cc: list[str] | None = None,
    reply_to_message_id: str | None = None,
    in_reply_to_db_id: str | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> dict:
    """Send an email from one of the Hostinger mailboxes via SMTP SSL (port 465).

    Records the outbound message in mailbox_emails for unified inbox visibility.

    Args:
        mailbox: one of loads|sales|info|mark|cece
        to: list of recipient addresses
        subject: email subject line
        body_html: HTML body (preferred)
        body_text: plain text body (fallback)
        cc: optional CC list
        reply_to_message_id: SMTP Message-ID to set In-Reply-To header
        in_reply_to_db_id: Eagle Eye DB id of the email being replied to
        attachments: list of (filename, bytes, content_type) tuples
    """
    if mailbox not in MAILBOX_ADDRESSES:
        raise ValueError(f"Unknown mailbox '{mailbox}'. Valid: {list(MAILBOX_ADDRESSES)}")

    from_address = MAILBOX_ADDRESSES[mailbox]
    password = getattr(get_settings(), f"email_{mailbox}_password", "")
    if not password:
        raise ValueError(
            f"SMTP password not configured for '{mailbox}'. "
            f"Set EMAIL_{mailbox.upper()}_PASSWORD environment variable."
        )

    # Build MIME message
    if attachments:
        msg = MIMEMultipart("mixed")
        alt = MIMEMultipart("alternative")
        if body_text:
            alt.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            alt.attach(MIMEText(body_html, "html", "utf-8"))
        if not body_text and not body_html:
            alt.attach(MIMEText("(no content)", "plain", "utf-8"))
        msg.attach(alt)
        for filename, data, content_type in attachments:
            part = MIMEApplication(data, Name=filename)
            part["Content-Disposition"] = f'attachment; filename="{filename}"'
            msg.attach(part)
    else:
        msg = MIMEMultipart("alternative")
        if body_text:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))
        if not body_text and not body_html:
            msg.attach(MIMEText("(no content)", "plain", "utf-8"))

    msg["From"] = f"3 Lakes Logistics <{from_address}>"
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    if reply_to_message_id:
        msg["In-Reply-To"] = reply_to_message_id
        msg["References"] = reply_to_message_id

    # Send via Hostinger SMTP (SSL on port 465 — use SMTP_SSL, not STARTTLS)
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.login(from_address, password)
            all_recipients = to + (cc or [])
            server.sendmail(from_address, all_recipients, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        raise ValueError(f"SMTP authentication failed for {from_address} — verify password")
    except smtplib.SMTPConnectError as exc:
        raise ValueError(f"SMTP connection to {SMTP_HOST}:{SMTP_PORT} failed: {exc}")
    except smtplib.SMTPException as exc:
        raise ValueError(f"SMTP error: {exc}")

    # Record in mailbox_emails (outbound)
    now = datetime.now(timezone.utc).isoformat()
    try:
        record: dict = {
            "mailbox":      mailbox,
            "direction":    "outbound",
            "from_address": from_address,
            "to_addresses": to,
            "cc_addresses": cc or [],
            "subject":      subject,
            "body_text":    body_text[:10000] if body_text else "",
            "body_html":    body_html[:10000] if body_html else "",
            "is_read":      True,
            "sent_at":      now,
            "received_at":  now,
        }
        if reply_to_message_id:
            record["thread_id"] = reply_to_message_id
        get_supabase().table("mailbox_emails").insert(record).execute()
    except Exception as exc:
        log.warning("Failed to record outbound email in DB: %s", exc)

    log.info("smtp sent from=%s to=%s subject=%r", from_address, to, subject)
    return {"sent": True, "from": from_address, "to": to, "subject": subject}


def send_transactional(
    to: str | list[str],
    subject: str,
    body_html: str = "",
    body_text: str = "",
    *,
    mailbox: str = "info",
    cc: list[str] | None = None,
) -> dict:
    """Send an automated/transactional email through an internal Hostinger mailbox.

    This is the consolidated path for all automated emails (welcome, onboarding,
    dispatch, settlement, agreements, reminders, internal reports). Cold-outreach
    blasts still go through Postmark — everything else routes here so it sends
    directly from loads@/sales@/info@ and shows up in the unified Email Center.

    Degrades gracefully: if the mailbox password isn't configured or the send
    fails, this logs and returns {"ok": False, ...} rather than raising, so
    background jobs and request handlers never crash on email delivery.

    Args:
        to: recipient address or list of addresses
        subject: subject line
        body_html: HTML body (preferred)
        body_text: plain-text body / fallback
        mailbox: which mailbox to send from — loads|sales|info|mark|cece
        cc: optional CC list
    """
    recipients = [to] if isinstance(to, str) else [r for r in (to or []) if r]
    recipients = [r for r in recipients if r]
    if not recipients:
        return {"ok": False, "reason": "no_recipient"}

    try:
        result = send_from_mailbox(
            mailbox=mailbox,
            to=recipients,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            cc=cc,
        )
        return {"ok": True, **result}
    except ValueError as exc:
        # Unknown mailbox or missing SMTP password — expected when not configured.
        log.info("send_transactional skipped (mailbox=%s): %s", mailbox, exc)
        return {"ok": False, "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001
        log.warning("send_transactional failed (mailbox=%s): %s", mailbox, exc)
        return {"ok": False, "error": str(exc)}

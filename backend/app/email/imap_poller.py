"""IMAP polling service — connects to all 5 Hostinger mailboxes and fetches new messages.

Runs every 2 minutes via APScheduler. For loads@ mailbox: auto-uploads PDF attachments
to Supabase Storage and triggers CLM extraction (rate cons, BOLs, PODs).

Hostinger IMAP: imap.hostinger.com:993 (SSL)
Credentials: full email address + password per mailbox (env vars).
"""
from __future__ import annotations

import email as _email_lib
import imaplib
import logging
import ssl
from datetime import datetime, timezone
from email.header import decode_header as _decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from ..settings import get_settings
from ..supabase_client import get_supabase

log = logging.getLogger("3ll.email.imap")

IMAP_HOST = "imap.hostinger.com"
IMAP_PORT = 993

# Body size caps. HTML emails (Checkr, newsletters, receipts) carry large inline
# CSS + hidden preheaders, so a tight cap can truncate before the visible content
# and leave the reader with a blank pane.
_MAX_HTML = 250_000
_MAX_TEXT = 50_000

MAILBOX_CONFIG = [
    {"name": "loads", "address": "loads@3lakeslogistics.com"},
    {"name": "sales", "address": "sales@3lakeslogistics.com"},
    {"name": "info",  "address": "info@3lakeslogistics.com"},
    {"name": "mark",  "address": "mark@3lakeslogistics.com"},
    {"name": "cece",  "address": "cece@3lakeslogistics.com"},
]

# In-memory status cache — reset on restart, refreshed per poll
_mailbox_status: dict[str, dict] = {}


def _get_password(name: str) -> str:
    return getattr(get_settings(), f"email_{name}_password", "")


def _decode_str(raw: str | bytes | None) -> str:
    if not raw:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        parts = _decode_header(raw)
        out = []
        for part, charset in parts:
            if isinstance(part, bytes):
                out.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                out.append(str(part))
        return "".join(out)
    except Exception:
        return str(raw)


def _parse_message(
    msg: _email_lib.message.Message,
    mailbox_name: str,
    imap_uid: str,
) -> tuple[dict, list[tuple[str, str, bytes]]]:
    """Parse an email.message.Message into a DB record + list of attachment bytes."""
    subject = _decode_str(msg.get("Subject", ""))
    from_raw = _decode_str(msg.get("From", ""))
    _, from_addr = parseaddr(from_raw)
    to_raw = _decode_str(msg.get("To", ""))
    cc_raw = _decode_str(msg.get("Cc", ""))
    message_id = (msg.get("Message-ID") or "").strip()
    in_reply_to = (msg.get("In-Reply-To") or "").strip()

    date_str = msg.get("Date", "")
    try:
        received_at = parsedate_to_datetime(date_str).isoformat() if date_str else datetime.now(timezone.utc).isoformat()
    except Exception:
        received_at = datetime.now(timezone.utc).isoformat()

    body_text = ""
    body_html = ""
    attachments: list[dict] = []
    attachment_bytes: list[tuple[str, str, bytes]] = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = part.get_content_disposition() or ""
            fname = _decode_str(part.get_filename() or "")

            if "attachment" in disp or fname:
                try:
                    data = part.get_payload(decode=True) or b""
                    attachments.append({
                        "name": fname or f"file.{ctype.split('/')[-1]}",
                        "content_type": ctype,
                        "size_kb": round(len(data) / 1024, 1),
                    })
                    if data:
                        attachment_bytes.append((fname or "attachment", ctype, data))
                except Exception as exc:
                    log.warning("Attachment read error %s: %s", fname, exc)
            elif ctype == "text/plain" and not body_text:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    body_text = (part.get_payload(decode=True) or b"").decode(charset, errors="replace")[:_MAX_TEXT]
                except Exception:
                    pass
            elif ctype == "text/html" and not body_html:
                try:
                    charset = part.get_content_charset() or "utf-8"
                    # HTML emails (Checkr, newsletters, receipts) carry large inline
                    # CSS/preheaders; a tight cap truncates before the visible body.
                    body_html = (part.get_payload(decode=True) or b"").decode(charset, errors="replace")[:_MAX_HTML]
                except Exception:
                    pass
    else:
        ctype = msg.get_content_type()
        try:
            charset = msg.get_content_charset() or "utf-8"
            _cap = _MAX_HTML if ctype == "text/html" else _MAX_TEXT
            content = (msg.get_payload(decode=True) or b"").decode(charset, errors="replace")[:_cap]
            if ctype == "text/html":
                body_html = content
            else:
                body_text = content
        except Exception:
            pass

    to_addrs = [a.strip() for a in to_raw.split(",") if a.strip()] if to_raw else []
    cc_addrs = [a.strip() for a in cc_raw.split(",") if a.strip()] if cc_raw else []

    record: dict[str, Any] = {
        "mailbox":          mailbox_name,
        "direction":        "inbound",
        "message_id":       message_id or None,
        "thread_id":        in_reply_to or None,
        "from_address":     from_addr or from_raw or "unknown",
        "to_addresses":     to_addrs,
        "cc_addresses":     cc_addrs,
        "subject":          subject[:500],
        "body_text":        body_text,
        "body_html":        body_html,
        "attachment_count": len(attachments),
        "attachments":      attachments,
        "is_read":          False,
        "imap_uid":         int(imap_uid) if imap_uid.isdigit() else None,
        "received_at":      received_at,
    }
    return record, attachment_bytes


def _upload_attachment_to_storage(email_id: str, filename: str, content_type: str, data: bytes) -> str | None:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    path = f"email/{email_id}/{safe}"
    try:
        get_supabase().storage.from_("documents").upload(
            path=path,
            file=data,
            file_options={"content-type": content_type or "application/octet-stream"},
        )
        return path
    except Exception as exc:
        log.warning("Storage upload failed for %s: %s", filename, exc)
        return None


def _process_loads_attachments(
    email_id: str,
    attachment_bytes: list[tuple[str, str, bytes]],
) -> None:
    """Upload PDFs from loads@ to vault and fire CLM extraction."""
    sb = get_supabase()
    for filename, content_type, data in attachment_bytes:
        is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")
        if not is_pdf:
            continue
        try:
            storage_path = _upload_attachment_to_storage(email_id, filename, content_type, data)
            if not storage_path:
                continue

            fname_lower = filename.lower()
            if any(t in fname_lower for t in ["bol", "bill of lading"]):
                doc_type = "bol"
            elif any(t in fname_lower for t in ["pod", "proof"]):
                doc_type = "pod"
            elif any(t in fname_lower for t in ["agreement", "broker packet"]):
                doc_type = "broker_agreement"
            else:
                doc_type = "rate_con"

            result = sb.table("document_vault").insert({
                "doc_type":     doc_type,
                "filename":     filename,
                "storage_path": storage_path,
                "bucket":       "documents",
                "file_size_kb": round(len(data) / 1024, 1),
                "mime_type":    content_type or "application/pdf",
                "scan_status":  "classified",
                "notes":        f"Email attachment from loads@ (email_id={email_id})",
            }).execute()

            if result.data:
                vault_id = result.data[0]["id"]
                from ..triggers import fire_vault_scan  # noqa: PLC0415
                fire_vault_scan(vault_id)
                log.info("loads@ attachment vaulted + scan queued: %s → %s", filename, vault_id)
        except Exception as exc:
            log.warning("loads@ attachment processing failed (%s): %s", filename, exc)


def poll_mailbox(name: str) -> dict:
    """Poll a single mailbox for new UNSEEN messages.

    Returns {mailbox, status, fetched, unread, error?}.
    """
    password = _get_password(name)
    cfg = next((m for m in MAILBOX_CONFIG if m["name"] == name), None)
    if not cfg:
        return {"mailbox": name, "status": "unknown", "fetched": 0}
    if not password:
        _mailbox_status[name] = {"status": "unconfigured", "unread": 0, "error": "Password not set in env"}
        return {"mailbox": name, "status": "unconfigured", "fetched": 0}

    address = cfg["address"]
    try:
        ctx = ssl.create_default_context()
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ctx) as conn:
            conn.login(address, password)
            conn.select("INBOX")

            # Count unread
            _, unread_data = conn.search(None, "UNSEEN")
            unseen_uids = unread_data[0].split() if unread_data[0] else []
            unread_count = len(unseen_uids)

            # Fetch the 50 newest unseen messages
            fetch_uids = unseen_uids[-50:]

            sb = get_supabase()
            fetched = 0

            for uid_bytes in fetch_uids:
                try:
                    _, msg_data = conn.fetch(uid_bytes, "(RFC822)")
                    if not msg_data or not msg_data[0]:
                        continue
                    raw = msg_data[0][1]
                    if not isinstance(raw, bytes):
                        continue

                    msg = _email_lib.message_from_bytes(raw)
                    record, att_bytes = _parse_message(msg, name, uid_bytes.decode())

                    # Dedup by Message-ID
                    mid = record.get("message_id")
                    if mid:
                        existing = sb.table("mailbox_emails").select("id").eq("message_id", mid).limit(1).execute()
                        if existing.data:
                            continue

                    insert_res = sb.table("mailbox_emails").insert(record).execute()
                    if not insert_res.data:
                        continue
                    email_id = insert_res.data[0]["id"]
                    fetched += 1

                    # Auto-process PDF attachments in loads@ mailbox
                    if name == "loads" and att_bytes:
                        _process_loads_attachments(email_id, att_bytes)

                except Exception as exc:
                    log.warning("poll_mailbox %s uid=%s: %s", name, uid_bytes, exc)

        _mailbox_status[name] = {
            "status":      "ok",
            "unread":      unread_count,
            "last_polled": datetime.now(timezone.utc).isoformat(),
        }
        log.info("poll_mailbox %s fetched=%d unread=%d", name, fetched, unread_count)
        return {"mailbox": name, "status": "ok", "fetched": fetched, "unread": unread_count}

    except imaplib.IMAP4.error as exc:
        err = str(exc)
        _mailbox_status[name] = {"status": "error", "unread": 0, "error": err}
        log.error("IMAP4 error %s: %s", name, exc)
        return {"mailbox": name, "status": "error", "error": err, "fetched": 0}
    except Exception as exc:
        err = str(exc)
        _mailbox_status[name] = {"status": "error", "unread": 0, "error": err}
        log.error("poll_mailbox failed %s: %s", name, exc)
        return {"mailbox": name, "status": "error", "error": err, "fetched": 0}


def poll_all() -> list[dict]:
    """Poll all 5 mailboxes — called by APScheduler every 2 minutes."""
    results = []
    for cfg in MAILBOX_CONFIG:
        try:
            results.append(poll_mailbox(cfg["name"]))
        except Exception as exc:
            results.append({"mailbox": cfg["name"], "status": "error", "error": str(exc), "fetched": 0})
    return results


def get_mailbox_statuses() -> list[dict]:
    """Return current status of all mailboxes (in-memory cache + config)."""
    out = []
    for cfg in MAILBOX_CONFIG:
        name = cfg["name"]
        cached = _mailbox_status.get(name, {})
        pw = _get_password(name)
        out.append({
            "name":        name,
            "address":     cfg["address"],
            "configured":  bool(pw),
            "status":      cached.get("status", "unconfigured" if not pw else "pending"),
            "unread":      cached.get("unread", 0),
            "last_polled": cached.get("last_polled"),
            "error":       cached.get("error"),
        })
    return out

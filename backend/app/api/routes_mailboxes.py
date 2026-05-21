"""Mailbox REST API — unified inbox for all 5 Hostinger mailboxes.

Endpoints:
  GET  /api/mailboxes                  — list mailboxes with status + unread count
  POST /api/mailboxes/poll             — trigger IMAP poll for all mailboxes
  POST /api/mailboxes/{name}/poll      — poll a single mailbox
  GET  /api/mailboxes/inbox            — unified inbox (all mailboxes)
  GET  /api/mailboxes/{name}/inbox     — single-mailbox inbox
  GET  /api/mailboxes/email/{id}       — email detail (marks as read)
  PATCH /api/mailboxes/email/{id}      — update is_read / is_starred
  DELETE /api/mailboxes/email/{id}     — delete email record
  POST /api/mailboxes/compose          — compose + send new email
  POST /api/mailboxes/reply/{id}       — reply to an email
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..api.deps import require_bearer
from ..supabase_client import get_supabase
from ..logging_service import get_logger

router = APIRouter()
log = get_logger("3ll.api.mailboxes")

_VALID_MAILBOXES = {"loads", "sales", "info", "mark", "cece"}


# ── Status + polling ──────────────────────────────────────────────────────────

@router.get("/mailboxes")
def list_mailboxes(_: str = Depends(require_bearer)) -> dict:
    """List all 5 mailboxes with IMAP connection status and unread counts."""
    from ..email.imap_poller import get_mailbox_statuses
    return {"ok": True, "mailboxes": get_mailbox_statuses()}


@router.post("/mailboxes/poll")
def poll_all_mailboxes(_: str = Depends(require_bearer)) -> dict:
    """Trigger IMAP poll for all 5 mailboxes. Returns per-mailbox results."""
    from ..email.imap_poller import poll_all
    results = poll_all()
    total_fetched = sum(r.get("fetched", 0) for r in results)
    return {"ok": True, "results": results, "total_fetched": total_fetched}


@router.post("/mailboxes/{name}/poll")
def poll_single_mailbox(name: str, _: str = Depends(require_bearer)) -> dict:
    """Trigger IMAP poll for a single mailbox."""
    if name not in _VALID_MAILBOXES:
        raise HTTPException(400, f"Unknown mailbox '{name}'. Valid: {sorted(_VALID_MAILBOXES)}")
    from ..email.imap_poller import poll_mailbox
    result = poll_mailbox(name)
    return {"ok": True, **result}


# ── Inbox ─────────────────────────────────────────────────────────────────────

@router.get("/mailboxes/inbox")
def unified_inbox(
    limit: int = 100,
    offset: int = 0,
    unread_only: bool = False,
    _: str = Depends(require_bearer),
) -> dict:
    """Return emails from all mailboxes sorted by received_at DESC."""
    sb = get_supabase()
    q = sb.table("mailbox_emails").select(
        "id,mailbox,direction,from_address,to_addresses,subject,body_text,"
        "attachment_count,attachments,is_read,is_starred,status,received_at,sent_at"
    )
    if unread_only:
        q = q.eq("is_read", False)
    result = q.order("received_at", desc=True).range(offset, offset + limit - 1).execute()
    unread = sb.table("mailbox_emails").select("id", count="exact").eq("is_read", False).execute()
    return {
        "ok": True,
        "count": len(result.data),
        "unread_total": unread.count or 0,
        "emails": result.data,
    }


@router.get("/mailboxes/{name}/inbox")
def mailbox_inbox(
    name: str,
    limit: int = 100,
    offset: int = 0,
    unread_only: bool = False,
    _: str = Depends(require_bearer),
) -> dict:
    """Return emails for a single mailbox sorted by received_at DESC."""
    if name not in _VALID_MAILBOXES:
        raise HTTPException(400, f"Unknown mailbox '{name}'")
    sb = get_supabase()
    q = sb.table("mailbox_emails").select(
        "id,mailbox,direction,from_address,to_addresses,subject,body_text,"
        "attachment_count,attachments,is_read,is_starred,status,received_at,sent_at"
    ).eq("mailbox", name)
    if unread_only:
        q = q.eq("is_read", False)
    result = q.order("received_at", desc=True).range(offset, offset + limit - 1).execute()
    unread = sb.table("mailbox_emails").select("id", count="exact").eq("mailbox", name).eq("is_read", False).execute()
    return {
        "ok": True,
        "mailbox": name,
        "count": len(result.data),
        "unread": unread.count or 0,
        "emails": result.data,
    }


# ── Single email ──────────────────────────────────────────────────────────────

@router.get("/mailboxes/email/{email_id}")
def get_email(email_id: str, _: str = Depends(require_bearer)) -> dict:
    """Fetch a single email and mark it as read."""
    sb = get_supabase()
    result = sb.table("mailbox_emails").select("*").eq("id", email_id).limit(1).execute()
    if not result.data:
        raise HTTPException(404, "Email not found")
    email = result.data[0]

    # Mark as read
    if not email.get("is_read"):
        sb.table("mailbox_emails").update({"is_read": True}).eq("id", email_id).execute()
        email["is_read"] = True

    return {"ok": True, "email": email}


@router.patch("/mailboxes/email/{email_id}")
def update_email(email_id: str, body: dict, _: str = Depends(require_bearer)) -> dict:
    """Update is_read or is_starred on an email."""
    allowed = {k: v for k, v in body.items() if k in ("is_read", "is_starred", "status")}
    if not allowed:
        raise HTTPException(400, "Nothing to update — allowed fields: is_read, is_starred, status")
    sb = get_supabase()
    sb.table("mailbox_emails").update(allowed).eq("id", email_id).execute()
    return {"ok": True, "email_id": email_id, "updated": allowed}


@router.delete("/mailboxes/email/{email_id}", status_code=204)
def delete_email(email_id: str, _: str = Depends(require_bearer)) -> None:
    """Delete an email record from Eagle Eye (does not affect mailbox server)."""
    get_supabase().table("mailbox_emails").delete().eq("id", email_id).execute()


# ── Compose + Reply ───────────────────────────────────────────────────────────

@router.post("/mailboxes/compose")
async def compose_email(body: dict, _: str = Depends(require_bearer)) -> dict:
    """Send a new email from one of the Hostinger mailboxes.

    Body: {from_mailbox, to: [str], subject, body_html?, body_text?, cc?: [str]}
    """
    from ..email.smtp_sender import send_from_mailbox

    mailbox = body.get("from_mailbox", "").strip()
    to = body.get("to") or []
    subject = body.get("subject", "").strip()
    body_html = body.get("body_html", "")
    body_text = body.get("body_text", "")
    cc = body.get("cc") or []

    if not mailbox:
        raise HTTPException(400, "from_mailbox is required")
    if not to or not to[0]:
        raise HTTPException(400, "At least one recipient (to) is required")
    if not subject:
        raise HTTPException(400, "subject is required")

    try:
        result = send_from_mailbox(
            mailbox=mailbox,
            to=to if isinstance(to, list) else [to],
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            cc=cc if isinstance(cc, list) else ([cc] if cc else []),
        )
        return {"ok": True, **result}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        log.error("compose_email failed: %s", exc)
        raise HTTPException(502, f"Send failed: {exc}")


@router.post("/mailboxes/reply/{email_id}")
async def reply_to_email(email_id: str, body: dict, _: str = Depends(require_bearer)) -> dict:
    """Reply to an existing email.

    Body: {body_html?, body_text?, cc?: [str]}
    """
    from ..email.smtp_sender import send_from_mailbox

    sb = get_supabase()
    orig = sb.table("mailbox_emails").select("*").eq("id", email_id).limit(1).execute()
    if not orig.data:
        raise HTTPException(404, "Email not found")
    original = orig.data[0]

    reply_to = original.get("from_address", "")
    if not reply_to:
        raise HTTPException(400, "Original email has no from_address to reply to")

    subj = original.get("subject", "")
    if not subj.startswith("Re:"):
        subj = f"Re: {subj}"

    body_html = body.get("body_html", "")
    body_text = body.get("body_text", "")
    cc = body.get("cc") or []
    mailbox = original.get("mailbox", "loads")

    try:
        result = send_from_mailbox(
            mailbox=mailbox,
            to=[reply_to],
            subject=subj,
            body_html=body_html,
            body_text=body_text,
            cc=cc if isinstance(cc, list) else ([cc] if cc else []),
            reply_to_message_id=original.get("message_id"),
            in_reply_to_db_id=email_id,
        )
        return {"ok": True, **result}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        log.error("reply_to_email failed: %s", exc)
        raise HTTPException(502, f"Reply failed: {exc}")

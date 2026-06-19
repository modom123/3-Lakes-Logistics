"""External webhooks: Stripe (Penny), Vapi (Vance), Motive (Orbit), Postmark (email engagement)."""
from __future__ import annotations
import hashlib
import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request

from ..agents import motive_webhook, penny, vance
from ..logging_service import get_logger
from ..settings import get_settings
from ..supabase_client import get_supabase

log = get_logger("webhooks")
router = APIRouter()


def _verify_hmac_header(body: bytes, header_value: str | None, secret: str | None, name: str) -> None:
    if not secret:
        return
    if not header_value:
        raise HTTPException(401, f"Missing {name} header")
    sig = header_value.removeprefix("sha256=")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig.lower()):
        raise HTTPException(401, f"Invalid {name} signature")


@router.post("/stripe")
async def stripe_webhook(request: Request) -> dict:
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        event = penny.verify_and_parse(payload, sig)
    except ValueError as e:
        raise HTTPException(400, str(e))
    penny.handle_event(event)
    return {"received": True}


@router.post("/vapi")
async def vapi_webhook(
    request: Request,
    x_vapi_signature: str | None = Header(default=None),
) -> dict:
    body = await request.body()
    s = get_settings()
    _verify_hmac_header(body, x_vapi_signature, getattr(s, "vapi_webhook_secret", None), "X-Vapi-Signature")
    vance.handle_vapi_event(await request.json())
    return {"received": True}


@router.post("/motive")
async def motive_webhook_endpoint(
    request: Request,
    x_motive_signature: str | None = Header(default=None),
) -> dict:
    body = await request.body()
    s = get_settings()
    _verify_hmac_header(body, x_motive_signature, getattr(s, "motive_webhook_secret", None), "X-Motive-Signature")
    motive_webhook.handle(await request.json())
    return {"received": True}


@router.post("/postmark")
async def postmark_webhook(request: Request) -> dict:
    """Postmark open/click tracking webhook.

    Postmark posts one event per record type: Open, Click, Bounce, SpamComplaint.
    We use MessageID to look up the prospect in lf_bd_outreach_log and update
    their engagement. Two+ opens within the sequence → auto-flag as 'contacted'
    so they get prioritised for a Bland AI call.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"received": True}

    record_type = payload.get("RecordType", "")
    message_id = payload.get("MessageID") or payload.get("MessageId")
    recipient = payload.get("Recipient", "")

    if not message_id or record_type not in ("Open", "Click", "Bounce", "SpamComplaint"):
        return {"received": True}

    now_iso = datetime.now(timezone.utc).isoformat()
    db = get_supabase()

    try:
        # Find the outreach log entry matching this message
        log_rows = (
            db.table("lf_bd_outreach_log")
            .select("id,prospect_id")
            .eq("message_id", message_id)
            .limit(1)
            .execute()
        ).data or []

        if not log_rows:
            log.info("postmark_webhook: no outreach log match for message_id=%s", message_id)
            return {"received": True}

        prospect_id = log_rows[0]["prospect_id"]

        if record_type in ("Bounce", "SpamComplaint"):
            # Suppress this contact — mark do_not_contact
            db.table("lf_bd_prospects").update({
                "do_not_contact": True,
                "status": "lost",
                "notes": f"Auto-suppressed: Postmark {record_type} on {now_iso[:10]}",
                "updated_at": now_iso,
            }).eq("id", prospect_id).execute()
            log.info("postmark_webhook: suppressed prospect_id=%s reason=%s", prospect_id, record_type)
            return {"received": True}

        # Open or Click — count how many engagement events this prospect has
        open_rows = (
            db.table("lf_bd_outreach_log")
            .select("id")
            .eq("prospect_id", prospect_id)
            .eq("channel", "email_open")
            .execute()
        ).data or []
        open_count = len(open_rows) + 1  # include this one

        # Log the engagement event
        db.table("lf_bd_outreach_log").insert({
            "prospect_id": prospect_id,
            "channel": "email_open" if record_type == "Open" else "email_click",
            "step": -1,
            "subject": f"{record_type} tracked — {recipient}",
            "status": "tracked",
            "message_id": message_id,
        }).execute()

        # Advance status to 'contacted' once they've opened 2+ times (warm signal)
        if open_count >= 2:
            prospect = (
                db.table("lf_bd_prospects")
                .select("status")
                .eq("id", prospect_id)
                .limit(1)
                .execute()
            ).data or [{}]
            current_status = (prospect[0].get("status") or "") if prospect else ""
            if current_status not in ("contacted", "active", "lost"):
                db.table("lf_bd_prospects").update({
                    "status": "contacted",
                    "updated_at": now_iso,
                }).eq("id", prospect_id).execute()
                log.info(
                    "postmark_webhook: escalated prospect_id=%s to contacted (opens=%d)",
                    prospect_id, open_count,
                )

    except Exception as exc:  # noqa: BLE001
        log.error("postmark_webhook: error processing message_id=%s: %s", message_id, exc)

    return {"received": True}

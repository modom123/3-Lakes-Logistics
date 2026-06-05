"""Shipper Brain — agent that handles shipper notifications, webhooks, and invoicing.

Actions:
  notify_shipper   — send email via PostMark when load status changes
  fire_webhook     — POST to shipper webhook_url with HMAC-SHA256 signature
  generate_invoice — create invoice record for a delivered shipper load

Usage:
    from .agents.shipper_brain import run
    result = await run({"action": "generate_invoice", "shipper_load_id": "..."})
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import httpx

from ..supabase_client import get_supabase
from ..logging_service import get_logger, log_agent
from ..settings import get_settings

log = get_logger(__name__)

_AGENT = "shipper_brain"


# ────────────────────────────────────────────────────────────────────────────
# EMAIL NOTIFICATION
# ────────────────────────────────────────────────────────────────────────────

async def _notify_shipper(payload: dict) -> dict:
    """Send transactional email to shipper when load status changes.

    Required payload keys: shipper_load_id (or load details inline), event
    """
    shipper_load_id = payload.get("shipper_load_id")
    event = payload.get("event", "status_change")

    if not shipper_load_id:
        return {"ok": False, "error": "shipper_load_id required"}

    # Fetch load + shipper details
    try:
        sl_result = get_supabase().table("shipper_loads").select(
            "id, status, tracking_token, origin_city, origin_state, dest_city, dest_state, "
            "total_rate, pickup_date, delivery_date, shipper_id"
        ).eq("id", shipper_load_id).single().execute()
        sl = sl_result.data

        shipper_result = get_supabase().table("shippers").select(
            "email, company_name, contact_name"
        ).eq("id", sl["shipper_id"]).single().execute()
        shipper = shipper_result.data
    except Exception as e:
        log.error("Failed to fetch load/shipper for notification: %s", e)
        return {"ok": False, "error": str(e)}

    settings = get_settings()
    postmark_token = settings.postmark_server_token
    if not postmark_token:
        log.warning("PostMark token not configured — skipping email")
        return {"ok": False, "error": "postmark not configured"}

    tracking_url = f"{settings.site_url}/track/{sl.get('tracking_token', '')}"

    subject_map = {
        "dispatched": "Your load has been dispatched — 3 Lakes Logistics",
        "in_transit": "Your freight is in transit — 3 Lakes Logistics",
        "picked_up":  "Freight picked up — 3 Lakes Logistics",
        "delivered":  "Your shipment has been delivered — 3 Lakes Logistics",
        "invoiced":   "Invoice ready — 3 Lakes Logistics",
    }
    subject = subject_map.get(event, f"Load update: {event} — 3 Lakes Logistics")

    body = (
        f"Hello {shipper.get('contact_name') or shipper.get('company_name')},\n\n"
        f"Your load from {sl.get('origin_city')}, {sl.get('origin_state')} "
        f"to {sl.get('dest_city')}, {sl.get('dest_state')} "
        f"is now: {event.upper().replace('_', ' ')}.\n\n"
        f"Track your shipment: {tracking_url}\n\n"
        f"Pickup: {sl.get('pickup_date') or 'TBD'}\n"
        f"Delivery: {sl.get('delivery_date') or 'TBD'}\n"
        f"Total Rate: ${sl.get('total_rate') or 0:,.2f}\n\n"
        f"Questions? Call us at {settings.shipper_dispatcher_phone}\n\n"
        f"— 3 Lakes Logistics Team"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.postmarkapp.com/email",
                json={
                    "From": settings.postmark_from_email,
                    "To": shipper["email"],
                    "Subject": subject,
                    "TextBody": body,
                    "MessageStream": "outbound",
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Postmark-Server-Token": postmark_token,
                },
            )
        delivered = 200 <= resp.status_code < 300
        log_agent(_AGENT, "notify_shipper", payload=payload, result=f"status={resp.status_code}")
        return {"ok": delivered, "http_status": resp.status_code}
    except Exception as e:
        log.error("PostMark send failed: %s", e)
        return {"ok": False, "error": str(e)}


# ────────────────────────────────────────────────────────────────────────────
# WEBHOOK DELIVERY
# ────────────────────────────────────────────────────────────────────────────

async def _fire_webhook(payload: dict) -> dict:
    """POST to shipper webhook_url with HMAC-SHA256 signature. Retries 3x with backoff.

    Required payload keys: shipper_id, event_type, data (dict)
    """
    shipper_id = payload.get("shipper_id")
    event_type = payload.get("event_type", "load.update")
    data = payload.get("data", {})

    if not shipper_id:
        return {"ok": False, "error": "shipper_id required"}

    try:
        result = get_supabase().table("shippers").select(
            "webhook_url, webhook_secret, webhook_events"
        ).eq("id", shipper_id).single().execute()
        shipper = result.data
    except Exception as e:
        return {"ok": False, "error": f"fetch shipper failed: {e}"}

    webhook_url = shipper.get("webhook_url")
    if not webhook_url:
        return {"ok": False, "error": "no webhook_url configured"}

    # Check if event is subscribed
    webhook_events = shipper.get("webhook_events") or []
    if webhook_events and event_type not in webhook_events:
        return {"ok": True, "skipped": True, "reason": f"event {event_type!r} not in subscribed events"}

    body_dict = {
        "event": event_type,
        "shipper_id": shipper_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    body_bytes = json.dumps(body_dict).encode()
    secret = shipper.get("webhook_secret", "")
    sig = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()

    http_status = None
    response_body = None
    delivered = False
    attempts = 0

    for attempt in range(1, 4):
        attempts = attempt
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    webhook_url,
                    content=body_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-3LL-Signature": f"sha256={sig}",
                        "X-3LL-Event": event_type,
                    },
                )
            http_status = resp.status_code
            response_body = resp.text[:500]
            if 200 <= resp.status_code < 300:
                delivered = True
                break
            # Non-2xx — retry
            log.warning("Webhook attempt %d got status %d", attempt, resp.status_code)
        except Exception as e:
            log.warning("Webhook attempt %d failed: %s", attempt, e)
            response_body = str(e)

        if attempt < 3:
            await asyncio.sleep(2 ** attempt)  # 2s, 4s backoff

    # Log delivery
    try:
        get_supabase().table("shipper_webhook_log").insert({
            "shipper_id": shipper_id,
            "event_type": event_type,
            "payload": body_dict,
            "http_status": http_status,
            "response_body": response_body,
            "delivered": delivered,
            "attempts": attempts,
        }).execute()
    except Exception as e:
        log.warning("Could not log webhook delivery: %s", e)

    log_agent(
        _AGENT, "fire_webhook",
        payload={"shipper_id": shipper_id, "event_type": event_type},
        result=f"delivered={delivered} status={http_status} attempts={attempts}",
    )

    return {
        "ok": delivered,
        "http_status": http_status,
        "attempts": attempts,
        "delivered": delivered,
    }


# ────────────────────────────────────────────────────────────────────────────
# INVOICE GENERATION
# ────────────────────────────────────────────────────────────────────────────

async def _generate_invoice(payload: dict) -> dict:
    """Create an invoice for a delivered shipper load.

    Required payload key: shipper_load_id
    Invoice number format: INV-{YEAR}-{5-digit-seq}
    """
    shipper_load_id = payload.get("shipper_load_id")
    if not shipper_load_id:
        return {"ok": False, "error": "shipper_load_id required"}

    try:
        sl_result = get_supabase().table("shipper_loads").select(
            "id, shipper_id, total_rate, invoice_number, status"
        ).eq("id", shipper_load_id).single().execute()
        sl = sl_result.data
    except Exception as e:
        return {"ok": False, "error": f"fetch load failed: {e}"}

    if not sl:
        return {"ok": False, "error": "load not found"}

    if sl.get("invoice_number"):
        return {"ok": True, "invoice_number": sl["invoice_number"], "already_exists": True}

    # Fetch payment terms from shipper
    payment_terms = 30
    try:
        sh_result = get_supabase().table("shippers").select("payment_terms").eq(
            "id", sl["shipper_id"]
        ).single().execute()
        payment_terms = sh_result.data.get("payment_terms", 30) if sh_result.data else 30
    except Exception:
        pass

    # Compute next invoice sequence number for this year
    year = datetime.now(timezone.utc).year
    seq = 1
    try:
        prefix = f"INV-{year}-"
        existing = get_supabase().table("shipper_loads").select(
            "invoice_number"
        ).like("invoice_number", f"{prefix}%").execute()

        if existing.data:
            seq_numbers = []
            for row in existing.data:
                try:
                    seq_numbers.append(int(row["invoice_number"].split("-")[-1]))
                except Exception:
                    pass
            if seq_numbers:
                seq = max(seq_numbers) + 1
    except Exception as e:
        log.warning("Could not compute invoice sequence: %s", e)

    invoice_number = f"INV-{year}-{seq:05d}"
    today = datetime.now(timezone.utc).date()
    due_date = today + timedelta(days=payment_terms)

    try:
        get_supabase().table("shipper_loads").update({
            "invoice_number": invoice_number,
            "invoice_amount": sl.get("total_rate"),
            "invoice_date": today.isoformat(),
            "invoice_due_date": due_date.isoformat(),
            "invoice_paid": False,
            "status": "invoiced",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", shipper_load_id).execute()
    except Exception as e:
        log.error("Failed to write invoice to DB: %s", e)
        return {"ok": False, "error": str(e)}

    # Update shipper total_spend
    try:
        get_supabase().rpc("increment_shipper_spend", {
            "p_shipper_id": sl["shipper_id"],
            "p_amount": sl.get("total_rate") or 0,
        }).execute()
    except Exception:
        pass

    log_agent(
        _AGENT, "generate_invoice",
        payload={"shipper_load_id": shipper_load_id},
        result=f"invoice_number={invoice_number}",
    )

    invoice = {
        "invoice_number": invoice_number,
        "invoice_amount": sl.get("total_rate"),
        "invoice_date": today.isoformat(),
        "invoice_due_date": due_date.isoformat(),
        "shipper_load_id": shipper_load_id,
        "shipper_id": sl["shipper_id"],
    }

    # Fire invoice webhook
    try:
        await _fire_webhook({
            "shipper_id": sl["shipper_id"],
            "event_type": "load.invoiced",
            "data": invoice,
        })
    except Exception as e:
        log.warning("Could not fire invoice webhook: %s", e)

    return {"ok": True, **invoice}


# ────────────────────────────────────────────────────────────────────────────
# DISPATCHER
# ────────────────────────────────────────────────────────────────────────────

async def run(payload: dict) -> dict:
    """Dispatch to the appropriate shipper brain action."""
    action = payload.get("action")

    if action == "notify_shipper":
        return await _notify_shipper(payload)
    elif action == "fire_webhook":
        return await _fire_webhook(payload)
    elif action == "generate_invoice":
        return await _generate_invoice(payload)
    else:
        log.error("shipper_brain: unknown action=%s", action)
        return {"ok": False, "error": f"unknown action: {action!r}"}

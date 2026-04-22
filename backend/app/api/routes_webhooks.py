"""External webhooks: Stripe (Penny), Vapi (Vance), Motive (Orbit), Twilio (Echo).

Stage 5 hardening (step 74):
- All signatures verified via `app.security.verify_*`.
- Every inbound lands in `webhook_log` with verified=true|false + payload.
- Stripe events are idempotent via `stripe_events.id` PK.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..agents import motive_webhook, penny, vance
from ..integrations import stripe_client
from ..integrations.sms import handle_inbound as sms_handle_inbound
from ..logging_service import get_logger
from ..security import (
    SignatureError, verify_motive, verify_stripe, verify_twilio, verify_vapi,
)

log = get_logger("webhooks")
router = APIRouter()


def _log_inbound(source: str, event_id: str | None, verified: bool, payload) -> None:
    try:
        from ..supabase_client import get_supabase
        get_supabase().table("webhook_log").insert({
            "source": source, "event_id": event_id,
            "verified": verified, "payload": payload,
        }).execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("webhook_log insert failed: %s", exc)


@router.post("/stripe")
async def stripe_webhook(request: Request) -> dict:
    body = await request.body()
    sig = request.headers.get("stripe-signature")
    try:
        verify_stripe(body, sig)
    except SignatureError as exc:
        _log_inbound("stripe", None, False, {"err": str(exc)})
        raise HTTPException(400, str(exc))
    event = stripe_client.safe_load(body)
    _log_inbound("stripe", event.get("id"), True, event)
    if stripe_client.record_event(event):
        penny.handle_event(event)
    return {"received": True}


@router.post("/vapi")
async def vapi_webhook(request: Request) -> dict:
    body = await request.body()
    sig = request.headers.get("x-vapi-signature")
    try:
        verify_vapi(body, sig)
    except SignatureError as exc:
        _log_inbound("vapi", None, False, {"err": str(exc)})
        raise HTTPException(400, str(exc))
    event = stripe_client.safe_load(body)
    _log_inbound("vapi", event.get("id"), True, event)
    vance.handle_vapi_event(event)
    return {"received": True}


@router.post("/motive")
async def motive_webhook_endpoint(request: Request) -> dict:
    body = await request.body()
    sig = request.headers.get("x-motive-signature")
    try:
        verify_motive(body, sig)
    except SignatureError as exc:
        _log_inbound("motive", None, False, {"err": str(exc)})
        raise HTTPException(400, str(exc))
    event = stripe_client.safe_load(body)
    _log_inbound("motive", event.get("event_id"), True, event)
    motive_webhook.handle(event)
    return {"received": True}


@router.post("/twilio/sms")
async def twilio_sms_webhook(request: Request) -> dict:
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    sig = request.headers.get("x-twilio-signature")
    url = str(request.url)
    try:
        verify_twilio(url, params, sig)
        verified = True
    except SignatureError as exc:
        _log_inbound("twilio", params.get("MessageSid"), False, {"err": str(exc)})
        raise HTTPException(400, str(exc))
    _log_inbound("twilio", params.get("MessageSid"), verified, params)
    kind = sms_handle_inbound(params.get("From") or "", params.get("Body") or "")
    return {"received": True, "handling": kind}

"""External webhooks: Stripe (Penny), Vapi (Vance), Motive (Orbit)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..agents import motive_webhook, penny, vance
from ..logging_service import get_logger

log = get_logger("webhooks")
router = APIRouter()


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
async def vapi_webhook(request: Request) -> dict:
    body = await request.json()
    vance.handle_vapi_event(body)
    return {"received": True}


@router.post("/motive")
async def motive_webhook_endpoint(request: Request) -> dict:
    body = await request.json()
    motive_webhook.handle(body)
    return {"received": True}

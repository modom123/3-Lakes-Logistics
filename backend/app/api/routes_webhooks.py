"""External webhooks: Stripe (Penny), Vapi (Vance), Motive (Orbit)."""
from __future__ import annotations
import hashlib
import hmac

from fastapi import APIRouter, Header, HTTPException, Request

from ..agents import motive_webhook, penny, vance
from ..logging_service import get_logger
from ..settings import get_settings

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

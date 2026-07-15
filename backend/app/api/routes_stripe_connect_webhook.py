"""Stripe Connect webhook — POST /api/webhooks/stripe-connect

Handles Connect account lifecycle events so a driver's payout status reflects
reality without anyone polling:

  account.updated → re-sync stripe_account_status / stripe_payouts_enabled for the
                    matching driver (light or heavy fleet).

Setup (Stripe Dashboard → Developers → Webhooks, a *Connect* endpoint):
  URL:    https://three-lakes-logistics-api.onrender.com/api/webhooks/stripe-connect
  Events: account.updated
  Secret: STRIPE_WEBHOOK_SECRET  (reuses the general webhook secret in settings)
"""
from __future__ import annotations

import json
import logging
from typing import Any

import stripe
from fastapi import APIRouter, Header, HTTPException, Request

from ..logging_service import log_agent
from ..payments import stripe_connect
from ..settings import get_settings

log = logging.getLogger("3ll.webhooks.stripe_connect")
router = APIRouter()


@router.post("/webhooks/stripe-connect")
async def stripe_connect_webhook(
    request: Request,
    stripe_signature: str | None = Header(None),
) -> dict[str, Any]:
    body = await request.body()
    s = get_settings()

    secret = s.stripe_webhook_secret
    if secret:
        try:
            stripe.api_key = s.stripe_secret_key
            event = stripe.Webhook.construct_event(body, stripe_signature, secret)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=401, detail="Invalid Stripe webhook signature")
    else:
        # No secret configured yet — parse without verification (dev/setup mode).
        try:
            event = json.loads(body)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("type") or ""
    obj = (event.get("data") or {}).get("object") or {}

    # For account.updated the object *is* the Connect account; its id is the
    # connected-account id we store as stripe_account_id.
    account_id = obj.get("id") or event.get("account") or ""

    log_agent(
        "stripe_connect_webhook",
        event_type,
        payload={"account_id": account_id},
    )

    if event_type != "account.updated":
        return {"ok": True, "action": "no_op", "event": event_type}

    if not account_id:
        return {"ok": True, "action": "no_account_id"}

    result = stripe_connect.sync_account_status(account_id)
    return {"ok": True, "action": "synced", "account_id": account_id, **result}

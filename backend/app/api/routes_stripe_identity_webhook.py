"""Stripe Identity webhook — POST /api/webhooks/stripe-identity

Events handled:
  identity.verification_session.verified       → approve driver, store license data
  identity.verification_session.requires_input → verification needs retry (SMS driver)
  identity.verification_session.canceled       → driver abandoned — log and notify

Setup in Stripe dashboard:
  Developers → Webhooks → Add endpoint
  URL: https://three-lakes-logistics-api.onrender.com/api/webhooks/stripe-identity
  Events: identity.verification_session.verified
          identity.verification_session.requires_input
          identity.verification_session.canceled

Set STRIPE_IDENTITY_WEBHOOK_SECRET in Render env vars after creating the webhook.
"""
from __future__ import annotations

import logging
from typing import Any

import stripe
from fastapi import APIRouter, Header, HTTPException, Request

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase

log = logging.getLogger("3ll.webhooks.stripe_identity")
router = APIRouter()

_RETRY_SMS = (
    "Hi! We had trouble reading your license photo — please try again. "
    "Check your email for a new verification link or call 661-466-9932 for help."
)


def _find_driver_by_session(sb, session_id: str) -> dict | None:
    try:
        r = (
            sb.table("light_vehicle_drivers")
            .select("*")
            .eq("stripe_verification_session_id", session_id)
            .maybe_single()
            .execute()
        )
        return r.data
    except Exception:  # noqa: BLE001
        return None


def _send_sms(phone: str, message: str) -> None:
    import re
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        phone = f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        phone = f"+{digits}"
    else:
        return
    s = get_settings()
    if s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number:
        try:
            from twilio.rest import Client
            Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                to=phone, from_=s.twilio_from_number, body=message
            )
        except Exception as e:  # noqa: BLE001
            log.warning("SMS failed: %s", e)


@router.post("/webhooks/stripe-identity")
async def stripe_identity_webhook(
    request: Request,
    stripe_signature: str | None = Header(None),
) -> dict[str, Any]:
    body = await request.body()
    s = get_settings()

    # Verify webhook signature
    secret = s.stripe_identity_webhook_secret
    if secret:
        try:
            stripe.api_key = s.stripe_secret_key
            event = stripe.Webhook.construct_event(body, stripe_signature, secret)
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=401, detail="Invalid Stripe webhook signature")
    else:
        # No secret configured yet — parse without verification (dev/setup mode)
        import json
        try:
            event = json.loads(body)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("type") or (event.get("type") if isinstance(event, dict) else "")
    session_obj = (event.get("data") or {}).get("object") or {}
    session_id  = session_obj.get("id") or ""
    status      = session_obj.get("status") or ""
    metadata    = session_obj.get("metadata") or {}
    driver_id   = metadata.get("driver_id") or ""

    log_agent("stripe_identity_webhook", event_type, payload={
        "session_id": session_id, "status": status, "driver_id": driver_id
    })

    sb = get_supabase()

    # Find driver — prefer metadata driver_id, fall back to session lookup
    driver = None
    if driver_id:
        try:
            r = sb.table("light_vehicle_drivers").select("*").eq("id", driver_id).maybe_single().execute()
            driver = r.data
        except Exception:  # noqa: BLE001
            pass

    if not driver and session_id:
        driver = _find_driver_by_session(sb, session_id)

    if not driver:
        log.warning("Stripe Identity webhook: no driver found — session_id=%s driver_id=%s", session_id, driver_id)
        return {"ok": True, "action": "no_matching_driver"}

    resolved_driver_id = str(driver["id"])

    # ── Verified ──────────────────────────────────────────────────────────────
    if event_type == "identity.verification_session.verified" or status == "verified":
        # Extract verified document data
        verified_outputs: dict = {}
        stripe.api_key = s.stripe_secret_key
        try:
            full_session = stripe.identity.VerificationSession.retrieve(
                session_id, expand=["verified_outputs"]
            )
            outputs = full_session.verified_outputs or {}
            verified_outputs = {
                "first_name":     getattr(outputs, "first_name", None),
                "last_name":      getattr(outputs, "last_name", None),
                "dob":            str(getattr(outputs, "dob", None) or ""),
                "id_number":      getattr(outputs, "id_number", None),
                "id_number_type": getattr(outputs, "id_number_type", None),
            }
        except Exception as e:  # noqa: BLE001
            log.warning("Could not retrieve verified outputs: %s", e)

        from ..agents import maya
        result = maya.approve_driver(resolved_driver_id, session_id, verified_outputs)
        log.info("Driver approved via Stripe Identity: %s", resolved_driver_id)
        return {"ok": True, "action": "driver_approved", **result}

    # ── Needs retry ───────────────────────────────────────────────────────────
    if event_type == "identity.verification_session.requires_input" or status == "requires_input":
        phone = driver.get("phone") or ""
        if phone:
            _send_sms(phone, _RETRY_SMS)
        log.info("Stripe Identity needs retry: driver=%s", resolved_driver_id)
        return {"ok": True, "action": "retry_needed", "driver_id": resolved_driver_id}

    # ── Canceled ──────────────────────────────────────────────────────────────
    if event_type == "identity.verification_session.canceled" or status == "canceled":
        log.info("Stripe Identity canceled: driver=%s", resolved_driver_id)
        return {"ok": True, "action": "verification_canceled", "driver_id": resolved_driver_id}

    return {"ok": True, "action": "no_op", "event": event_type}

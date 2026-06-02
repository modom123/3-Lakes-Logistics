"""Stripe Identity client — driver license verification for Light Fleet.

Stripe Identity lets drivers scan their license with their phone camera.
Stripe verifies it's real, not expired, and extracts the data automatically.
Cost: ~$1.50 per verification. No business approval required — works with
your existing Stripe account.

Docs: https://stripe.com/docs/identity
Dashboard: https://dashboard.stripe.com/identity

Flow:
  1. create_verification_session(driver_id, email)
     → returns a client_secret the front-end uses to open Stripe's hosted flow
     OR a url for redirect-based flow
  2. Driver scans license on their phone (Stripe handles camera + OCR)
  3. Stripe calls POST /api/webhooks/stripe-identity when verification completes
  4. identity.verification_session.verified   → extract license data, approve driver
     identity.verification_session.requires_input → needs retry (blurry photo etc.)
     identity.verification_session.canceled    → driver abandoned flow

Environment variables required:
  STRIPE_SECRET_KEY           — already set (used for payments too)
  STRIPE_IDENTITY_WEBHOOK_SECRET — set this after adding the webhook in Stripe dashboard
"""
from __future__ import annotations

from typing import Any

import stripe

from ..logging_service import log_agent
from ..settings import get_settings

_NAME = "stripe_identity_client"


def _sk() -> str:
    s = get_settings()
    if not s.stripe_secret_key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")
    stripe.api_key = s.stripe_secret_key
    return s.stripe_secret_key


def create_verification_session(
    driver_id: str,
    email: str,
    name: str,
    return_url: str = "https://3lakeslogistics.com/driver-verified",
) -> dict[str, Any]:
    """
    Create a Stripe Identity VerificationSession.

    Returns:
      session_id      — store on the driver row (for webhook matching)
      url             — redirect the driver here to complete verification
      client_secret   — use with Stripe.js if doing in-page flow (optional)
    """
    try:
        _sk()
        session = stripe.identity.VerificationSession.create(
            type="document",
            metadata={
                "driver_id": driver_id,
                "email": email,
                "name": name,
            },
            options={
                "document": {
                    "allowed_types": ["driving_license"],
                    "require_id_number": False,
                    "require_live_capture": True,
                    "require_matching_selfie": False,  # license scan only, no selfie
                }
            },
            return_url=return_url,
        )
        log_agent(_NAME, "session_created", payload={"driver_id": driver_id}, result=session.id)
        return {
            "created": True,
            "session_id": session.id,
            "url": session.url,
            "client_secret": session.client_secret,
            "status": session.status,
        }
    except stripe.error.StripeError as e:
        return {"created": False, "error": str(e)}
    except RuntimeError as e:
        return {"created": False, "error": str(e)}


def get_session(session_id: str) -> dict[str, Any]:
    """Retrieve a VerificationSession and its extracted document data."""
    try:
        _sk()
        session = stripe.identity.VerificationSession.retrieve(
            session_id,
            expand=["verified_outputs"],
        )
        outputs = session.verified_outputs or {}
        doc = getattr(outputs, "document", None) or {}

        return {
            "session_id": session_id,
            "status": session.status,   # 'verified' | 'requires_input' | 'canceled' | 'processing'
            "last_error": getattr(session, "last_error", None),
            "verified_outputs": {
                "first_name":      getattr(outputs, "first_name", None),
                "last_name":       getattr(outputs, "last_name", None),
                "dob":             str(getattr(outputs, "dob", None) or ""),
                "id_number":       getattr(outputs, "id_number", None),   # license number
                "id_number_type":  getattr(outputs, "id_number_type", None),
                "address":         getattr(outputs, "address", None),
            },
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def cancel_session(session_id: str) -> dict[str, Any]:
    """Cancel a pending verification session."""
    try:
        _sk()
        session = stripe.identity.VerificationSession.cancel(session_id)
        return {"cancelled": True, "status": session.status}
    except Exception as e:  # noqa: BLE001
        return {"cancelled": False, "error": str(e)[:200]}


def verify_webhook(payload: bytes, sig_header: str | None, secret: str) -> stripe.Event:
    """
    Verify and parse a Stripe Identity webhook event.
    Raises stripe.error.SignatureVerificationError if invalid.
    """
    return stripe.Webhook.construct_event(payload, sig_header, secret)


def ping() -> dict[str, Any]:
    """Test the Stripe connection and Identity product availability."""
    try:
        _sk()
        # Verify Identity is enabled by listing sessions (limit 1)
        stripe.identity.VerificationSession.list(limit=1)
        return {"connected": True, "platform": "stripe_identity"}
    except RuntimeError as e:
        return {"connected": False, "platform": "stripe_identity", "error": str(e)}
    except stripe.error.StripeError as e:
        return {"connected": False, "platform": "stripe_identity", "error": str(e)}

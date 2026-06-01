"""Penny — Steps 17, 29-30. Stripe subscription lifecycle."""
from __future__ import annotations

from typing import Any

import stripe

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase


def _sk() -> str:
    s = get_settings().stripe_secret_key
    if not s:
        raise RuntimeError("STRIPE_SECRET_KEY not set")
    stripe.api_key = s
    return s


def create_checkout_session(carrier_id: str, plan: str, email: str, founders_truck_count: int = 1) -> str | None:
    """Step 17: after intake we hand the carrier a Stripe checkout URL."""
    s = get_settings()
    if not s.stripe_secret_key or not s.stripe_price_founders:
        log_agent("penny", "checkout", carrier_id=carrier_id, error="stripe_not_configured")
        return None
    try:
        _sk()
        quantity = founders_truck_count if plan == "founders" else 1
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=email,
            line_items=[{"price": s.stripe_price_founders, "quantity": quantity}],
            success_url="https://3lakeslogistics.com/welcome?cid=" + carrier_id,
            cancel_url="https://3lakeslogistics.com/?cid=" + carrier_id,
            metadata={"carrier_id": carrier_id, "plan": plan, "founders_truck_count": str(founders_truck_count)},
        )
        get_supabase().table("active_carriers").update(
            {"stripe_customer_id": session.customer or None}
        ).eq("id", carrier_id).execute()
        log_agent("penny", "checkout_created", carrier_id=carrier_id, result=session.id)
        return session.url
    except Exception as e:  # noqa: BLE001
        log_agent("penny", "checkout", carrier_id=carrier_id, error=str(e))
        return None


def verify_and_parse(payload: bytes, sig: str | None) -> dict[str, Any]:
    _sk()
    secret = get_settings().stripe_webhook_secret
    if not secret or not sig:
        raise ValueError("webhook signature not configured")
    event = stripe.Webhook.construct_event(payload, sig, secret)
    return event


def handle_event(event: dict[str, Any]) -> None:
    """Steps 29-30: invoice.paid → activate; invoice.payment_failed → suspend."""
    etype = event.get("type")
    data = event.get("data", {}).get("object", {})
    carrier_id = (data.get("metadata") or {}).get("carrier_id")
    sb = get_supabase()

    if etype == "checkout.session.completed" and carrier_id:
        sb.table("active_carriers").update({
            "subscription_status": "active",
            "stripe_subscription_id": data.get("subscription"),
            "status": "active",
            "onboarded_at": "now()",
        }).eq("id", carrier_id).execute()
        log_agent("penny", "activated", carrier_id=carrier_id, result=etype)

    elif etype == "invoice.payment_failed" and carrier_id:
        sb.table("active_carriers").update({
            "subscription_status": "past_due", "status": "suspended",
        }).eq("id", carrier_id).execute()
        log_agent("penny", "suspended", carrier_id=carrier_id, result=etype)

    elif etype == "customer.subscription.deleted" and carrier_id:
        sb.table("active_carriers").update({
            "subscription_status": "canceled", "status": "churned",
        }).eq("id", carrier_id).execute()

    elif etype == "payment_intent.succeeded" and carrier_id:
        # Advance onboarding: run step 14 (esign.send_agreement) then mark payment confirmed
        try:
            from ..execution_engine.executor import run_step  # noqa: PLC0415
            run_step(14, carrier_id, None, {"trigger": "payment_intent.succeeded"})
        except Exception as exc:  # noqa: BLE001
            log_agent("penny", "step14_failed", carrier_id=carrier_id, error=str(exc))
        try:
            sb.table("active_carriers").update({
                "status": "payment_confirmed",
            }).eq("id", carrier_id).execute()
        except Exception as exc:  # noqa: BLE001
            log_agent("penny", "status_update_failed", carrier_id=carrier_id, error=str(exc))
        log_agent("penny", "payment_intent_succeeded", carrier_id=carrier_id, result=etype)


def run(payload: dict[str, Any]) -> dict[str, Any]:
    log_agent("penny", "manual_run", payload=payload, result="noop")
    return {"agent": "penny", "status": "ok"}

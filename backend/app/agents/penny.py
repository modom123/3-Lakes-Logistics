"""Penny — Billing & subscription lifecycle (Stage 5 step 65)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..integrations.email import send_email
from ..integrations.stripe_client import create_checkout_session as _checkout
from ..logging_service import log_agent


def create_checkout(carrier_id: str, plan: str, email: str) -> str | None:
    res = _checkout(
        plan=plan, carrier_id=carrier_id,
        success_url=f"https://3lakeslogistics.com/welcome?cid={carrier_id}",
        cancel_url=f"https://3lakeslogistics.com/?cid={carrier_id}",
    )
    if res.get("status") != "ok":
        log_agent("penny", "checkout_failed", carrier_id=carrier_id,
                  error=res.get("error") or res.get("reason"))
        return None
    log_agent("penny", "checkout_created", carrier_id=carrier_id, result=res.get("id"))
    return res.get("url")


def handle_event(event: dict[str, Any]) -> dict[str, Any]:
    """Apply a verified Stripe event to the active_carriers row."""
    etype = event.get("type") or ""
    obj = (event.get("data") or {}).get("object") or {}
    carrier_id = (obj.get("metadata") or {}).get("carrier_id") or obj.get("client_reference_id")
    email = obj.get("customer_email") or obj.get("receipt_email")
    now = datetime.now(timezone.utc).isoformat()

    patch: dict[str, Any] = {}
    if etype == "checkout.session.completed":
        patch = {
            "subscription_status": "active",
            "stripe_customer_id": obj.get("customer"),
            "stripe_subscription_id": obj.get("subscription"),
            "status": "active",
            "onboarded_at": now,
        }
    elif etype == "customer.subscription.updated":
        patch = {"subscription_status": obj.get("status") or "active"}
    elif etype == "invoice.payment_succeeded":
        patch = {"subscription_status": "active", "status": "active"}
        if email:
            send_email(email, "Payment received", "<p>Thanks — your 3 Lakes Logistics subscription is current.</p>", tag="payment_ok")
    elif etype == "invoice.payment_failed":
        patch = {"subscription_status": "past_due", "status": "suspended"}
        if email:
            send_email(email, "Payment failed — action needed",
                       "<p>We couldn't charge your card. Please update billing in your portal.</p>", tag="dunning_1")
    elif etype == "customer.subscription.deleted":
        patch = {"subscription_status": "canceled", "status": "churned"}

    if carrier_id and patch:
        try:
            from ..supabase_client import get_supabase
            get_supabase().table("active_carriers").update(patch).eq("id", carrier_id).execute()
        except Exception as exc:  # noqa: BLE001
            log_agent("penny", "update_failed", carrier_id=carrier_id, error=str(exc))
            return {"status": "error", "error": str(exc)}

    log_agent("penny", f"event:{etype}", carrier_id=carrier_id, result="applied" if patch else "ignored")
    return {"status": "ok", "applied": bool(patch), "type": etype}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind") or "noop"
    if kind == "apply_event":
        return {"agent": "penny", **handle_event(payload.get("event") or {})}
    if kind == "checkout":
        url = create_checkout(payload.get("carrier_id"), payload.get("plan") or "founders",
                              payload.get("email") or "")
        return {"agent": "penny", "status": "ok" if url else "error", "url": url}
    return {"agent": "penny", "status": "ok", "note": "no-op"}

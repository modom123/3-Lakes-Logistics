"""Stripe helpers (step 73 gating + step 74 webhook handling)."""
from __future__ import annotations

import json

import httpx

from ..logging_service import get_logger
from ..settings import get_settings

_log = get_logger("3ll.stripe")

PLAN_PRICE_MAP = {
    "founders": "stripe_price_founders",
    "pro":      "stripe_price_pro",
    "scale":    "stripe_price_scale",
}


def price_id(plan: str) -> str | None:
    key = PLAN_PRICE_MAP.get((plan or "").lower())
    if not key:
        return None
    return getattr(get_settings(), key, "") or None


def create_checkout_session(plan: str, carrier_id: str, success_url: str, cancel_url: str) -> dict:
    s = get_settings()
    price = price_id(plan)
    if not (s.stripe_secret_key and price):
        return {"status": "stub", "reason": "stripe_not_configured"}
    try:
        r = httpx.post(
            "https://api.stripe.com/v1/checkout/sessions",
            auth=(s.stripe_secret_key, ""),
            data={
                "mode": "subscription",
                "line_items[0][price]": price,
                "line_items[0][quantity]": 1,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "client_reference_id": carrier_id,
                "metadata[carrier_id]": carrier_id,
                "metadata[plan]": plan,
            },
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        return {"status": "ok", "id": data.get("id"), "url": data.get("url")}
    except Exception as exc:  # noqa: BLE001
        _log.exception("stripe checkout failed")
        return {"status": "error", "error": str(exc)}


def record_event(event: dict) -> bool:
    """Persist a verified Stripe event. Returns True when a new row is created."""
    try:
        from ..supabase_client import get_supabase
        carrier_id = _carrier_from_event(event)
        ins = get_supabase().table("stripe_events").insert({
            "id": event.get("id"),
            "type": event.get("type"),
            "carrier_id": carrier_id,
            "data": event,
        }).execute()
        return bool(ins.data)
    except Exception as exc:  # noqa: BLE001
        if "duplicate" in str(exc).lower():
            return False
        _log.exception("stripe_events insert failed")
        return False


def _carrier_from_event(event: dict) -> str | None:
    obj = (event.get("data") or {}).get("object") or {}
    return (
        (obj.get("metadata") or {}).get("carrier_id")
        or obj.get("client_reference_id")
    )


def safe_load(body: bytes) -> dict:
    try:
        return json.loads(body.decode() or "{}")
    except Exception:  # noqa: BLE001
        return {}

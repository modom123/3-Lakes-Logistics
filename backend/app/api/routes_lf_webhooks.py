"""Inbound webhooks from Curri and Roadie.

Curri  → POST /api/webhooks/curri
Roadie → POST /api/webhooks/roadie

Both endpoints:
 1. Verify the webhook signature (HMAC-SHA256)
 2. Parse the event
 3. Update the corresponding light_vehicle_trips row
 4. Trigger downstream agents (Rio for new loads, Cash for completions)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response

from ..settings import get_settings
from ..supabase_client import get_supabase
from ..logging_service import log_agent

log = logging.getLogger("3ll.webhooks.lf")
router = APIRouter()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _verify_hmac(body: bytes, signature: str | None, secret: str, prefix: str = "sha256=") -> bool:
    if not secret or not signature:
        return True  # skip verification if secret not configured yet
    expected = prefix + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _find_trip_by_external_id(sb, external_id: str) -> dict | None:
    try:
        r = (
            sb.table("light_vehicle_trips")
            .select("*")
            .eq("external_id", external_id)
            .maybe_single()
            .execute()
        )
        return r.data
    except Exception:  # noqa: BLE001
        return None


def _update_trip(sb, external_id: str, updates: dict) -> bool:
    try:
        updates["updated_at"] = _now_iso()
        sb.table("light_vehicle_trips").update(updates).eq("external_id", external_id).execute()
        return True
    except Exception:  # noqa: BLE001
        return False


def _maybe_auto_queue(event_data: dict, source: str) -> None:
    """If a new order/gig arrives and we have no matching trip, queue it."""
    try:
        from ..agents import kai, rio
        load = {
            "segment": "courier",
            "source": source,
            "external_id": event_data.get("id") or event_data.get("order_id") or event_data.get("gig_id"),
            "pickup_address": (
                event_data.get("pickup_address")
                or (event_data.get("pickup") or {}).get("address")
            ),
            "dropoff_address": (
                event_data.get("delivery_address")
                or (event_data.get("delivery") or {}).get("address")
            ),
            "passenger_name": (
                event_data.get("contact_name")
                or (event_data.get("pickup") or {}).get("contact", {}).get("name")
            ),
            "passenger_phone": (
                event_data.get("contact_phone")
                or (event_data.get("pickup") or {}).get("contact", {}).get("phone")
            ),
            "scheduled_at": event_data.get("scheduled_at") or event_data.get("pickup_by") or event_data.get("pickup_after"),
            "rate_total": event_data.get("carrier_pay") or event_data.get("driver_pay") or event_data.get("rate"),
        }
        result = kai.queue_trip(load)
        if result.get("queued") and result.get("trip_id"):
            rio.dispatch_trip(result["trip_id"])
    except Exception as e:  # noqa: BLE001
        log.warning("Auto-queue failed: %s", e)


# ── Curri webhook ─────────────────────────────────────────────────────────────

_CURRI_STATUS_MAP = {
    "order.available":        None,
    "order.accepted":         "assigned",
    "order.picked_up":        "in_progress",
    "order.delivered":        "completed",
    "order.cancelled":        "cancelled",
    "order.status_updated":   None,
}

@router.post("/webhooks/curri")
async def curri_webhook(
    request: Request,
    x_curri_signature: str | None = Header(None),
) -> dict[str, Any]:
    body = await request.body()
    s = get_settings()

    if not _verify_hmac(body, x_curri_signature, s.curri_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid Curri webhook signature")

    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("event") or event.get("type") or ""
    data = event.get("data") or event.get("order") or event
    order_id = str(data.get("id") or data.get("order_id") or "")

    log_agent("curri_webhook", event_type, payload={"order_id": order_id})

    sb = get_supabase()
    new_status = _CURRI_STATUS_MAP.get(event_type)

    if event_type == "order.available":
        _maybe_auto_queue(data, "curri")
        return {"ok": True, "action": "auto_queued"}

    if new_status and order_id:
        updated = _update_trip(sb, order_id, {"status": new_status})

        if new_status == "completed":
            trip = _find_trip_by_external_id(sb, order_id)
            if trip and trip.get("id"):
                try:
                    from ..agents import cash
                    trip_id = str(trip["id"])
                    sb.table("light_vehicle_trips").update({"status": "completed", "completed_at": _now_iso()}).eq("id", trip_id).execute()
                    cash.settle_trip(trip_id)
                except Exception as e:  # noqa: BLE001
                    log.warning("Auto-settle failed: %s", e)

        return {"ok": True, "updated": updated, "status": new_status}

    return {"ok": True, "action": "no_op", "event": event_type}


# ── Roadie webhook ────────────────────────────────────────────────────────────

_ROADIE_STATUS_MAP = {
    "shipment.created":         "pending",
    "shipment.driver_assigned": "assigned",
    "shipment.picked_up":       "in_progress",
    "shipment.delivered":       "completed",
    "shipment.cancelled":       "cancelled",
    "shipment.eta_updated":     None,
    "gig.available":            None,
    "gig.claimed":              "assigned",
    "gig.picked_up":            "in_progress",
    "gig.delivered":            "completed",
    "gig.cancelled":            "cancelled",
}

@router.post("/webhooks/roadie")
async def roadie_webhook(
    request: Request,
    x_roadie_signature: str | None = Header(None),
) -> dict[str, Any]:
    body = await request.body()
    s = get_settings()

    if not _verify_hmac(body, x_roadie_signature, s.roadie_webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid Roadie webhook signature")

    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("event") or event.get("type") or ""
    data = event.get("data") or event.get("shipment") or event.get("gig") or event
    shipment_id = str(data.get("id") or data.get("shipment_id") or data.get("gig_id") or "")

    log_agent("roadie_webhook", event_type, payload={"shipment_id": shipment_id})

    sb = get_supabase()
    new_status = _ROADIE_STATUS_MAP.get(event_type)

    if event_type == "gig.available":
        _maybe_auto_queue(data, "roadie")
        return {"ok": True, "action": "auto_queued"}

    if new_status and shipment_id:
        updated = _update_trip(sb, shipment_id, {"status": new_status})

        if new_status == "completed":
            trip = _find_trip_by_external_id(sb, shipment_id)
            if trip and trip.get("id"):
                try:
                    from ..agents import cash
                    trip_id = str(trip["id"])
                    sb.table("light_vehicle_trips").update({"status": "completed", "completed_at": _now_iso()}).eq("id", trip_id).execute()
                    cash.settle_trip(trip_id)
                except Exception as e:  # noqa: BLE001
                    log.warning("Auto-settle failed: %s", e)

        return {"ok": True, "updated": updated, "status": new_status}

    return {"ok": True, "action": "no_op", "event": event_type}

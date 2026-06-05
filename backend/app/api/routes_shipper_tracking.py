"""Public shipment tracking — no authentication required.

Endpoints:
  GET /api/track/{token} — public tracking page data by tracking token
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..supabase_client import get_supabase
from ..logging_service import get_logger
from ..settings import get_settings

log = get_logger(__name__)

router = APIRouter()


@router.get("/track/{token}")
async def track_shipment(token: str):
    """Public endpoint: look up a shipment by tracking token.

    Returns origin, destination, current location, status, timeline, and docs.
    No shipper auth required — safe to share with end customers.
    """
    try:
        result = get_supabase().table("shipper_loads").select(
            "id, load_id, status, "
            "origin_city, origin_state, "
            "dest_city, dest_state, "
            "pickup_date, delivery_date, "
            "eta, current_lat, current_lng, current_city, current_state, last_update, "
            "bol_url, pod_url, "
            "created_at, updated_at"
        ).eq("tracking_token", token).single().execute()

        sl = result.data
    except Exception:
        sl = None

    if not sl:
        raise HTTPException(status_code=404, detail="tracking token not found")

    # Build load number from id (3LL-XXXX)
    short_id = sl["id"].replace("-", "").upper()[:8]
    load_number = f"3LL-{short_id}"

    # Pull latest telemetry if in transit
    current_location = None
    if sl.get("load_id") and sl.get("status") in ("dispatched", "in_transit", "picked_up"):
        try:
            telem_result = get_supabase().table("truck_telemetry").select(
                "lat, lng, city, state, recorded_at"
            ).eq("load_id", sl["load_id"]).order(
                "recorded_at", desc=True
            ).limit(1).execute()

            if telem_result.data:
                t = telem_result.data[0]
                current_location = {
                    "lat": t.get("lat"),
                    "lng": t.get("lng"),
                    "city": t.get("city"),
                    "state": t.get("state"),
                    "last_update": t.get("recorded_at"),
                }
        except Exception as e:
            log.warning("Could not fetch telemetry for tracking token %s: %s", token, e)

    # Fall back to stored GPS on the shipper_load record
    if not current_location and sl.get("current_lat"):
        current_location = {
            "lat": sl.get("current_lat"),
            "lng": sl.get("current_lng"),
            "city": sl.get("current_city"),
            "state": sl.get("current_state"),
            "last_update": sl.get("last_update"),
        }

    # Build timeline
    timeline = []
    try:
        log_result = get_supabase().table("agent_log").select(
            "action, created_at, result"
        ).contains("payload", {"shipper_load_id": sl["id"]}).order(
            "created_at", desc=False
        ).limit(30).execute()

        for row in (log_result.data or []):
            timeline.append({
                "event": row.get("action"),
                "timestamp": row.get("created_at"),
                "description": row.get("result"),
            })
    except Exception:
        pass

    # Fallback timeline from status
    if not timeline:
        status_labels = {
            "quote": "Quote created",
            "booked": "Load booked — awaiting dispatch",
            "dispatched": "Driver dispatched",
            "picked_up": "Freight picked up",
            "in_transit": "In transit",
            "delivered": "Delivered",
            "cancelled": "Cancelled",
            "invoiced": "Invoice sent",
        }
        timeline.append({
            "event": sl["status"],
            "timestamp": sl.get("updated_at") or sl.get("created_at"),
            "description": status_labels.get(sl["status"], sl["status"]),
        })
        if sl["status"] in ("quote", "booked"):
            timeline.insert(0, {
                "event": "created",
                "timestamp": sl.get("created_at"),
                "description": "Load request submitted",
            })

    # Dispatcher contact from settings (never expose driver personal info)
    try:
        dispatcher_phone = get_settings().shipper_dispatcher_phone
    except Exception:
        dispatcher_phone = "+13135469006"

    return {
        "load_number": load_number,
        "status": sl["status"],
        "origin": {
            "city": sl.get("origin_city"),
            "state": sl.get("origin_state"),
        },
        "destination": {
            "city": sl.get("dest_city"),
            "state": sl.get("dest_state"),
        },
        "pickup_date": sl.get("pickup_date"),
        "delivery_date": sl.get("delivery_date"),
        "eta": sl.get("eta"),
        "current_location": current_location,
        "timeline": timeline,
        "documents": {
            "bol_available": bool(sl.get("bol_url")),
            "pod_available": bool(sl.get("pod_url")),
        },
        "carrier_contact": dispatcher_phone,
    }

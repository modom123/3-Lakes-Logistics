"""Shipper portal — loads, quotes, invoices, account management, webhooks.

All endpoints require a valid shipper session token (Bearer).
"""
from __future__ import annotations

import math
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..supabase_client import get_supabase
from ..logging_service import get_logger, log_agent
from .routes_shipper_auth import ShipperSession

log = get_logger(__name__)

router = APIRouter()


# ────────────────────────────────────────────────────────────────────────────
# STATE CENTROIDS  (lat, lng) for haversine distance estimate
# ────────────────────────────────────────────────────────────────────────────

_STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "AL": (32.806671, -86.791130),
    "AK": (61.370716, -152.404419),
    "AZ": (33.729759, -111.431221),
    "AR": (34.969704, -92.373123),
    "CA": (36.116203, -119.681564),
    "CO": (39.059811, -105.311104),
    "CT": (41.597782, -72.755371),
    "DE": (39.318523, -75.507141),
    "FL": (27.766279, -81.686783),
    "GA": (33.040619, -83.643074),
    "HI": (21.094318, -157.498337),
    "ID": (44.240459, -114.478828),
    "IL": (40.349457, -88.986137),
    "IN": (39.849426, -86.258278),
    "IA": (42.011539, -93.210526),
    "KS": (38.526600, -96.726486),
    "KY": (37.668140, -84.670067),
    "LA": (31.169960, -91.867805),
    "ME": (44.693947, -69.381927),
    "MD": (39.063946, -76.802101),
    "MA": (42.230171, -71.530106),
    "MI": (43.326618, -84.536095),
    "MN": (45.694454, -93.900192),
    "MS": (32.741646, -89.678696),
    "MO": (38.456085, -92.288368),
    "MT": (46.921925, -110.454353),
    "NE": (41.125370, -98.268082),
    "NV": (38.313515, -117.055374),
    "NH": (43.452492, -71.563896),
    "NJ": (40.298904, -74.521011),
    "NM": (34.840515, -106.248482),
    "NY": (42.165726, -74.948051),
    "NC": (35.630066, -79.806419),
    "ND": (47.528912, -99.784012),
    "OH": (40.388783, -82.764915),
    "OK": (35.565342, -96.928917),
    "OR": (44.572021, -122.070938),
    "PA": (40.590752, -77.209755),
    "RI": (41.680893, -71.511780),
    "SC": (33.856892, -80.945007),
    "SD": (44.299782, -99.438828),
    "TN": (35.747845, -86.692345),
    "TX": (31.054487, -97.563461),
    "UT": (40.150032, -111.862434),
    "VT": (44.045876, -72.710686),
    "VA": (37.769337, -78.169968),
    "WA": (47.400902, -121.490494),
    "WV": (38.491226, -80.954453),
    "WI": (44.268543, -89.616508),
    "WY": (42.755966, -107.302490),
    "DC": (38.897438, -77.026817),
}


# ────────────────────────────────────────────────────────────────────────────
# RATE ENGINE
# ────────────────────────────────────────────────────────────────────────────

def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance in miles between two lat/lng points."""
    R = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _calculate_rate(
    origin_state: str,
    dest_state: str,
    load_type: str,
    weight_lbs: float,
    hazmat: bool = False,
    temp_controlled: bool = False,
) -> dict:
    """Calculate freight rate. Returns pricing dict."""
    RPM = {
        "dry_van":  2.80,
        "flatbed":  3.10,
        "reefer":   3.30,
        "step_deck": 3.00,
        "hotshot":  2.60,
    }

    origin_coords = _STATE_CENTROIDS.get(origin_state.upper())
    dest_coords = _STATE_CENTROIDS.get(dest_state.upper())

    if not origin_coords or not dest_coords:
        # Fallback: assume 500 miles
        air_miles = 500.0
    else:
        air_miles = _haversine_miles(
            origin_coords[0], origin_coords[1],
            dest_coords[0], dest_coords[1],
        )

    road_miles = air_miles * 1.25
    rpm = RPM.get(load_type.lower(), 2.80)
    base_rate = road_miles * rpm

    # Surcharges
    fuel_surcharge = base_rate * 0.18
    accessorial_fees = 0.0
    if hazmat:
        accessorial_fees += base_rate * 0.10
    if temp_controlled:
        accessorial_fees += base_rate * 0.08

    total_raw = base_rate + fuel_surcharge + accessorial_fees
    total_raw = max(total_raw, 650.0)

    # Round to nearest $25
    total_rate = round(total_raw / 25) * 25
    # Scale fuel/access proportionally so they sum to total_rate
    ratio = total_rate / total_raw if total_raw else 1.0
    base_rate = round(base_rate * ratio, 2)
    fuel_surcharge = round(fuel_surcharge * ratio, 2)
    accessorial_fees = round(accessorial_fees * ratio, 2)
    rate_per_mile = round(total_rate / road_miles, 4) if road_miles else 0.0

    return {
        "quoted_miles": round(road_miles, 1),
        "base_rate": base_rate,
        "fuel_surcharge": fuel_surcharge,
        "accessorial_fees": accessorial_fees,
        "total_rate": float(total_rate),
        "rate_per_mile": rate_per_mile,
    }


# ────────────────────────────────────────────────────────────────────────────
# MODELS
# ────────────────────────────────────────────────────────────────────────────

class QuoteRequest(BaseModel):
    origin_city: str
    origin_state: str
    dest_city: str
    dest_state: str
    load_type: str = "dry_van"
    weight_lbs: float = 40000
    pallets: int = 26
    hazmat: bool = False
    temp_controlled: bool = False
    pickup_date: str | None = None
    delivery_date: str | None = None


class LoadSubmitRequest(BaseModel):
    # Quote fields (optional if submitting fresh)
    quote_id: str | None = None
    origin_address: str | None = None
    origin_city: str
    origin_state: str
    origin_zip: str | None = None
    origin_contact: str | None = None
    origin_phone: str | None = None
    pickup_date: str | None = None
    pickup_window_start: str | None = None
    pickup_window_end: str | None = None
    dest_address: str | None = None
    dest_city: str
    dest_state: str
    dest_zip: str | None = None
    dest_contact: str | None = None
    dest_phone: str | None = None
    delivery_date: str | None = None
    delivery_window_start: str | None = None
    delivery_window_end: str | None = None
    commodity: str | None = None
    weight_lbs: float = 40000
    pallets: int | None = None
    load_type: str = "dry_van"
    hazmat: bool = False
    hazmat_class: str | None = None
    temp_controlled: bool = False
    temp_min_f: float | None = None
    temp_max_f: float | None = None
    stackable: bool = True
    special_instructions: str | None = None
    # Rates (from quote or manual)
    quoted_miles: float | None = None
    base_rate: float | None = None
    fuel_surcharge: float | None = None
    accessorial_fees: float = 0
    total_rate: float | None = None
    rate_per_mile: float | None = None


class WebhookUpdateRequest(BaseModel):
    webhook_url: str | None = None
    webhook_events: list[str] | None = None


# ────────────────────────────────────────────────────────────────────────────
# QUOTE
# ────────────────────────────────────────────────────────────────────────────

@router.post("/quote")
async def get_quote(req: QuoteRequest, session: ShipperSession):
    """Calculate a freight rate quote."""
    try:
        pricing = _calculate_rate(
            origin_state=req.origin_state,
            dest_state=req.dest_state,
            load_type=req.load_type,
            weight_lbs=req.weight_lbs,
            hazmat=req.hazmat,
            temp_controlled=req.temp_controlled,
        )
    except Exception as e:
        log.error("Rate calculation failed: %s", e)
        raise HTTPException(status_code=500, detail="rate calculation failed")

    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    quote_id = str(uuid.uuid4())

    return {
        "quote_id": quote_id,
        "origin_city": req.origin_city,
        "origin_state": req.origin_state,
        "dest_city": req.dest_city,
        "dest_state": req.dest_state,
        "load_type": req.load_type,
        "weight_lbs": req.weight_lbs,
        "pallets": req.pallets,
        **pricing,
        "expires_at": expires_at.isoformat(),
    }


# ────────────────────────────────────────────────────────────────────────────
# LOADS
# ────────────────────────────────────────────────────────────────────────────

@router.post("/loads")
async def submit_load(req: LoadSubmitRequest, session: ShipperSession):
    """Submit a load booking. Creates shipper_loads + a linked loads record."""
    shipper_id = session["shipper_id"]

    # If rates not provided, calculate them
    if req.total_rate is None:
        pricing = _calculate_rate(
            origin_state=req.origin_state,
            dest_state=req.dest_state,
            load_type=req.load_type,
            weight_lbs=req.weight_lbs,
            hazmat=req.hazmat,
            temp_controlled=req.temp_controlled,
        )
        quoted_miles = pricing["quoted_miles"]
        base_rate = pricing["base_rate"]
        fuel_surcharge = pricing["fuel_surcharge"]
        accessorial_fees = pricing["accessorial_fees"]
        total_rate = pricing["total_rate"]
        rate_per_mile = pricing["rate_per_mile"]
    else:
        quoted_miles = req.quoted_miles
        base_rate = req.base_rate
        fuel_surcharge = req.fuel_surcharge
        accessorial_fees = req.accessorial_fees
        total_rate = req.total_rate
        rate_per_mile = req.rate_per_mile

    # Create the shipper_loads record
    try:
        sl_result = get_supabase().table("shipper_loads").insert({
            "shipper_id": shipper_id,
            "origin_address": req.origin_address,
            "origin_city": req.origin_city,
            "origin_state": req.origin_state,
            "origin_zip": req.origin_zip,
            "origin_contact": req.origin_contact,
            "origin_phone": req.origin_phone,
            "pickup_date": req.pickup_date,
            "pickup_window_start": req.pickup_window_start,
            "pickup_window_end": req.pickup_window_end,
            "dest_address": req.dest_address,
            "dest_city": req.dest_city,
            "dest_state": req.dest_state,
            "dest_zip": req.dest_zip,
            "dest_contact": req.dest_contact,
            "dest_phone": req.dest_phone,
            "delivery_date": req.delivery_date,
            "delivery_window_start": req.delivery_window_start,
            "delivery_window_end": req.delivery_window_end,
            "commodity": req.commodity,
            "weight_lbs": req.weight_lbs,
            "pallets": req.pallets,
            "load_type": req.load_type,
            "hazmat": req.hazmat,
            "hazmat_class": req.hazmat_class,
            "temp_controlled": req.temp_controlled,
            "temp_min_f": req.temp_min_f,
            "temp_max_f": req.temp_max_f,
            "stackable": req.stackable,
            "special_instructions": req.special_instructions,
            "quoted_miles": quoted_miles,
            "base_rate": base_rate,
            "fuel_surcharge": fuel_surcharge,
            "accessorial_fees": accessorial_fees,
            "total_rate": total_rate,
            "rate_per_mile": rate_per_mile,
            "status": "booked",
        }).execute()

        sl = sl_result.data[0]
    except Exception as e:
        log.error("Failed to create shipper_loads record: %s", e)
        raise HTTPException(status_code=500, detail="failed to create load")

    # Attempt to create a linked loads record in the main loads table
    linked_load_id = None
    try:
        load_result = get_supabase().table("loads").insert({
            "origin_city": req.origin_city,
            "origin_state": req.origin_state,
            "dest_city": req.dest_city,
            "dest_state": req.dest_state,
            "pickup_date": req.pickup_date,
            "delivery_date": req.delivery_date,
            "commodity": req.commodity,
            "weight": req.weight_lbs,
            "rate": total_rate,
            "status": "available",
            "source": "shipper_portal",
        }).execute()

        if load_result.data:
            linked_load_id = load_result.data[0]["id"]
            # Update shipper_load with load_id link
            get_supabase().table("shipper_loads").update(
                {"load_id": linked_load_id}
            ).eq("id", sl["id"]).execute()
    except Exception as e:
        log.warning("Could not create linked loads record (non-fatal): %s", e)

    # Bump shipper total_loads
    try:
        get_supabase().rpc("increment_shipper_loads", {"p_shipper_id": shipper_id}).execute()
    except Exception:
        pass  # non-fatal

    log_agent(
        "shipper_portal",
        "load_booked",
        payload={"shipper_id": shipper_id, "shipper_load_id": sl["id"]},
        result="booked",
    )

    return {
        "id": sl["id"],
        "load_id": linked_load_id,
        "tracking_token": sl.get("tracking_token"),
        "status": sl["status"],
        "total_rate": total_rate,
        "origin": f"{req.origin_city}, {req.origin_state}",
        "destination": f"{req.dest_city}, {req.dest_state}",
        "pickup_date": req.pickup_date,
        "delivery_date": req.delivery_date,
        "created_at": sl.get("created_at"),
    }


@router.get("/loads")
async def list_loads(
    session: ShipperSession,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
):
    """List shipper's loads with optional status filter."""
    shipper_id = session["shipper_id"]

    try:
        q = get_supabase().table("shipper_loads").select(
            "id, tracking_token, status, origin_city, origin_state, dest_city, dest_state, "
            "pickup_date, delivery_date, total_rate, load_type, commodity, weight_lbs, "
            "invoice_number, created_at, updated_at"
        ).eq("shipper_id", shipper_id).order("created_at", desc=True).range(offset, offset + limit - 1)

        if status:
            q = q.eq("status", status)

        result = q.execute()
        items = result.data or []

        return {"count": len(items), "items": items}
    except Exception as e:
        log.error("Failed to list shipper loads: %s", e)
        raise HTTPException(status_code=500, detail="failed to list loads")


@router.get("/loads/{load_id}")
async def get_load(load_id: str, session: ShipperSession):
    """Get load detail including GPS and timeline."""
    shipper_id = session["shipper_id"]

    try:
        result = get_supabase().table("shipper_loads").select("*").eq(
            "id", load_id
        ).eq("shipper_id", shipper_id).single().execute()

        sl = result.data
        if not sl:
            raise HTTPException(status_code=404, detail="load not found")
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to fetch load %s: %s", load_id, e)
        raise HTTPException(status_code=500, detail="failed to fetch load")

    # Attach latest telemetry if in transit
    telemetry = None
    if sl.get("load_id") and sl.get("status") in ("dispatched", "in_transit", "picked_up"):
        try:
            telem_result = get_supabase().table("truck_telemetry").select(
                "lat, lng, city, state, recorded_at, speed_mph"
            ).eq("load_id", sl["load_id"]).order("recorded_at", desc=True).limit(1).execute()
            if telem_result.data:
                telemetry = telem_result.data[0]
        except Exception as e:
            log.warning("Could not fetch telemetry for load %s: %s", load_id, e)

    # Fetch timeline events from agent_log if possible
    timeline = []
    try:
        log_result = get_supabase().table("agent_log").select(
            "action, created_at, result"
        ).contains("payload", {"shipper_load_id": load_id}).order(
            "created_at", desc=False
        ).limit(20).execute()
        for row in (log_result.data or []):
            timeline.append({
                "event": row.get("action"),
                "timestamp": row.get("created_at"),
                "description": row.get("result"),
            })
    except Exception:
        pass  # non-fatal, timeline stays empty

    # Fallback: single status event
    if not timeline:
        timeline.append({
            "event": sl["status"],
            "timestamp": sl.get("updated_at"),
            "description": f"Load is {sl['status']}",
        })

    return {
        **sl,
        "current_location": telemetry,
        "timeline": timeline,
    }


@router.delete("/loads/{load_id}")
async def cancel_load(load_id: str, session: ShipperSession):
    """Cancel a load (only quote/booked status allowed)."""
    shipper_id = session["shipper_id"]

    try:
        result = get_supabase().table("shipper_loads").select(
            "id, status"
        ).eq("id", load_id).eq("shipper_id", shipper_id).single().execute()

        sl = result.data
        if not sl:
            raise HTTPException(status_code=404, detail="load not found")
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to fetch load for cancellation: %s", e)
        raise HTTPException(status_code=500, detail="failed to fetch load")

    if sl["status"] not in ("quote", "booked"):
        raise HTTPException(
            status_code=409,
            detail=f"cannot cancel load in status '{sl['status']}'"
        )

    try:
        get_supabase().table("shipper_loads").update({
            "status": "cancelled",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", load_id).execute()

        return {"ok": True, "status": "cancelled"}
    except Exception as e:
        log.error("Failed to cancel load %s: %s", load_id, e)
        raise HTTPException(status_code=500, detail="failed to cancel load")


@router.get("/loads/{load_id}/documents")
async def get_load_documents(load_id: str, session: ShipperSession):
    """Get document URLs for a load."""
    shipper_id = session["shipper_id"]

    try:
        result = get_supabase().table("shipper_loads").select(
            "id, bol_url, pod_url"
        ).eq("id", load_id).eq("shipper_id", shipper_id).single().execute()

        sl = result.data
        if not sl:
            raise HTTPException(status_code=404, detail="load not found")

        return {
            "load_id": sl["id"],
            "bol_url": sl.get("bol_url"),
            "pod_url": sl.get("pod_url"),
            "bol_available": bool(sl.get("bol_url")),
            "pod_available": bool(sl.get("pod_url")),
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to fetch documents for load %s: %s", load_id, e)
        raise HTTPException(status_code=500, detail="failed to fetch documents")


# ────────────────────────────────────────────────────────────────────────────
# INVOICES
# ────────────────────────────────────────────────────────────────────────────

@router.get("/invoices")
async def list_invoices(
    session: ShipperSession,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
):
    """List invoices (shipper_loads where invoice_number is not null)."""
    shipper_id = session["shipper_id"]

    try:
        result = get_supabase().table("shipper_loads").select(
            "id, invoice_number, invoice_amount, invoice_date, invoice_due_date, "
            "invoice_paid, invoice_paid_date, total_rate, status, "
            "origin_city, origin_state, dest_city, dest_state, created_at"
        ).eq("shipper_id", shipper_id).not_.is_(
            "invoice_number", "null"
        ).order("invoice_date", desc=True).range(offset, offset + limit - 1).execute()

        items = result.data or []
        return {"count": len(items), "items": items}
    except Exception as e:
        log.error("Failed to list invoices: %s", e)
        raise HTTPException(status_code=500, detail="failed to list invoices")


@router.get("/invoices/{invoice_number}")
async def get_invoice(invoice_number: str, session: ShipperSession):
    """Get invoice detail."""
    shipper_id = session["shipper_id"]

    try:
        result = get_supabase().table("shipper_loads").select("*").eq(
            "invoice_number", invoice_number
        ).eq("shipper_id", shipper_id).single().execute()

        sl = result.data
        if not sl:
            raise HTTPException(status_code=404, detail="invoice not found")

        return sl
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to fetch invoice %s: %s", invoice_number, e)
        raise HTTPException(status_code=500, detail="failed to fetch invoice")


# ────────────────────────────────────────────────────────────────────────────
# ACCOUNT
# ────────────────────────────────────────────────────────────────────────────

@router.get("/account")
async def get_account(session: ShipperSession):
    """Full account info including monthly stats."""
    shipper_id = session["shipper_id"]

    try:
        result = get_supabase().table("shippers").select(
            "id, company_name, email, phone, address, city, state, zip, "
            "contact_name, status, credit_limit, payment_terms, "
            "total_loads, total_spend, created_at"
        ).eq("id", shipper_id).single().execute()

        shipper = result.data
        if not shipper:
            raise HTTPException(status_code=404, detail="shipper not found")
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to fetch shipper account: %s", e)
        raise HTTPException(status_code=500, detail="failed to fetch account")

    # This-month stats
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    this_month_loads = 0
    this_month_spend = 0.0
    try:
        m_result = get_supabase().table("shipper_loads").select(
            "total_rate"
        ).eq("shipper_id", shipper_id).neq("status", "cancelled").gte(
            "created_at", month_start.isoformat()
        ).execute()

        if m_result.data:
            this_month_loads = len(m_result.data)
            this_month_spend = sum(r.get("total_rate") or 0.0 for r in m_result.data)
    except Exception as e:
        log.warning("Could not compute monthly stats: %s", e)

    return {
        **shipper,
        "this_month_loads": this_month_loads,
        "this_month_spend": this_month_spend,
    }


@router.get("/account/api-key")
async def get_api_key(session: ShipperSession):
    """Return the shipper's current API key."""
    shipper_id = session["shipper_id"]

    try:
        result = get_supabase().table("shippers").select("api_key").eq(
            "id", shipper_id
        ).single().execute()

        return {"api_key": result.data.get("api_key") if result.data else None}
    except Exception as e:
        log.error("Failed to fetch api key: %s", e)
        raise HTTPException(status_code=500, detail="failed to fetch API key")


@router.post("/account/api-key/rotate")
async def rotate_api_key(session: ShipperSession):
    """Generate a new API key and return it."""
    shipper_id = session["shipper_id"]
    new_key = secrets.token_hex(32)

    try:
        get_supabase().table("shippers").update({
            "api_key": new_key,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", shipper_id).execute()

        return {"api_key": new_key}
    except Exception as e:
        log.error("Failed to rotate api key: %s", e)
        raise HTTPException(status_code=500, detail="failed to rotate API key")


# ────────────────────────────────────────────────────────────────────────────
# WEBHOOK CONFIG
# ────────────────────────────────────────────────────────────────────────────

@router.get("/webhook")
async def get_webhook_config(session: ShipperSession):
    """Get webhook configuration."""
    shipper_id = session["shipper_id"]

    try:
        result = get_supabase().table("shippers").select(
            "webhook_url, webhook_events, webhook_secret"
        ).eq("id", shipper_id).single().execute()

        return result.data or {}
    except Exception as e:
        log.error("Failed to fetch webhook config: %s", e)
        raise HTTPException(status_code=500, detail="failed to fetch webhook config")


@router.patch("/webhook")
async def update_webhook_config(req: WebhookUpdateRequest, session: ShipperSession):
    """Update webhook URL and/or events."""
    shipper_id = session["shipper_id"]

    updates: dict[str, Any] = {}
    if req.webhook_url is not None:
        updates["webhook_url"] = req.webhook_url
    if req.webhook_events is not None:
        updates["webhook_events"] = req.webhook_events

    if not updates:
        raise HTTPException(status_code=400, detail="no fields provided")

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        get_supabase().table("shippers").update(updates).eq("id", shipper_id).execute()
        return {"ok": True, **updates}
    except Exception as e:
        log.error("Failed to update webhook config: %s", e)
        raise HTTPException(status_code=500, detail="failed to update webhook config")


@router.post("/webhook/test")
async def test_webhook(session: ShipperSession):
    """Send a test payload to the configured webhook URL."""
    import httpx

    shipper_id = session["shipper_id"]

    try:
        result = get_supabase().table("shippers").select(
            "webhook_url, webhook_secret, company_name"
        ).eq("id", shipper_id).single().execute()

        shipper = result.data
    except Exception as e:
        log.error("Failed to fetch shipper for webhook test: %s", e)
        raise HTTPException(status_code=500, detail="failed to fetch shipper")

    webhook_url = shipper.get("webhook_url")
    if not webhook_url:
        raise HTTPException(status_code=400, detail="no webhook URL configured")

    import hashlib
    import hmac
    import json

    payload = {
        "event": "test",
        "shipper_id": shipper_id,
        "company_name": shipper.get("company_name"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": "3 Lakes Logistics webhook test",
    }
    payload_bytes = json.dumps(payload).encode()
    secret = shipper.get("webhook_secret", "")
    sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

    http_status = None
    response_body = None
    delivered = False
    error_msg = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                webhook_url,
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-3LL-Signature": f"sha256={sig}",
                    "X-3LL-Event": "test",
                },
            )
        http_status = resp.status_code
        response_body = resp.text[:500]
        delivered = 200 <= resp.status_code < 300
    except Exception as e:
        error_msg = str(e)
        log.warning("Webhook test delivery failed: %s", e)

    # Log the attempt
    try:
        get_supabase().table("shipper_webhook_log").insert({
            "shipper_id": shipper_id,
            "event_type": "test",
            "payload": payload,
            "http_status": http_status,
            "response_body": response_body,
            "delivered": delivered,
            "attempts": 1,
        }).execute()
    except Exception as e:
        log.warning("Could not log webhook test: %s", e)

    return {
        "delivered": delivered,
        "http_status": http_status,
        "error": error_msg,
    }


# ────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(session: ShipperSession):
    """Shipper dashboard summary."""
    shipper_id = session["shipper_id"]

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    active_loads = 0
    delivered_this_month = 0
    pending_invoices = 0
    total_spend_this_month = 0.0
    recent_loads = []
    alerts = []

    try:
        # Active loads
        active_result = get_supabase().table("shipper_loads").select(
            "id", count="exact"
        ).eq("shipper_id", shipper_id).in_(
            "status", ["booked", "dispatched", "in_transit", "picked_up"]
        ).execute()
        active_loads = active_result.count or 0

        # Delivered this month
        del_result = get_supabase().table("shipper_loads").select(
            "id", count="exact"
        ).eq("shipper_id", shipper_id).eq("status", "delivered").gte(
            "updated_at", month_start.isoformat()
        ).execute()
        delivered_this_month = del_result.count or 0

        # Pending invoices (has invoice but unpaid)
        inv_result = get_supabase().table("shipper_loads").select(
            "id", count="exact"
        ).eq("shipper_id", shipper_id).eq("invoice_paid", False).not_.is_(
            "invoice_number", "null"
        ).execute()
        pending_invoices = inv_result.count or 0

        # Spend this month
        spend_result = get_supabase().table("shipper_loads").select(
            "total_rate"
        ).eq("shipper_id", shipper_id).neq("status", "cancelled").gte(
            "created_at", month_start.isoformat()
        ).execute()
        if spend_result.data:
            total_spend_this_month = sum(r.get("total_rate") or 0.0 for r in spend_result.data)

        # Recent loads
        recent_result = get_supabase().table("shipper_loads").select(
            "id, tracking_token, status, origin_city, origin_state, dest_city, dest_state, "
            "total_rate, pickup_date, delivery_date, created_at"
        ).eq("shipper_id", shipper_id).order(
            "created_at", desc=True
        ).limit(5).execute()
        recent_loads = recent_result.data or []

    except Exception as e:
        log.error("Dashboard query failed: %s", e)
        raise HTTPException(status_code=500, detail="failed to load dashboard")

    # Build alerts
    if pending_invoices > 0:
        alerts.append({
            "type": "invoice",
            "message": f"{pending_invoices} unpaid invoice(s) outstanding",
        })

    return {
        "active_loads": active_loads,
        "delivered_this_month": delivered_this_month,
        "pending_invoices": pending_invoices,
        "total_spend_this_month": total_spend_this_month,
        "recent_loads": recent_loads,
        "alerts": alerts,
    }

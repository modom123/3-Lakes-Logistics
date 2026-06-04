"""Light Fleet module — SUV/Car services for 3 Lakes Logistics.

Covers the BIG 4 service types:
  - nemt        Non-Emergency Medical Transport (Medicaid rides, specimen delivery)
  - executive   VIP/airport/corporate transfers
  - courier     Same-day parcel, document, urban last-mile delivery
  - gig         Light vehicle driver pool management (no CDL required)
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response

from ..supabase_client import get_supabase
from .deps import require_bearer
from .routes_driver_auth import _send_falcon_lf_welcome, normalize_phone

router = APIRouter(dependencies=[Depends(require_bearer)])

# Public router — no auth required (self-service driver signup)
public_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mtd_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def _today_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _require_trip(sb, trip_id: str) -> dict:
    res = sb.table("light_vehicle_trips").select("*").eq("id", trip_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Trip not found")
    return res.data[0]


# ===========================================================================
# KPIs
# ===========================================================================

@router.get("/kpis")
def light_fleet_kpis() -> dict:
    """
    Aggregate KPI tile data for the Light Fleet home screen.

    Returns:
    - Trips per service type (nemt / executive / courier / gig)
    - Trips per status (pending / assigned / in_progress / completed / cancelled)
    - Month-to-date revenue (sum of rate_total on completed trips)
    - Active driver count
    - Today's trip count
    """
    sb = get_supabase()
    mtd = _mtd_iso()
    today = _today_iso()

    # All trips (for type + status breakdown)
    all_trips_res = sb.table("light_vehicle_trips").select("trip_type,status,rate_total,completed_at").execute()
    all_trips = all_trips_res.data or []

    # Count per type
    type_counts: dict[str, int] = {"nemt": 0, "executive": 0, "courier": 0, "gig": 0}
    for t in all_trips:
        tt = t.get("trip_type")
        if tt in type_counts:
            type_counts[tt] += 1

    # Count per status
    status_counts: dict[str, int] = {
        "pending": 0,
        "assigned": 0,
        "in_progress": 0,
        "completed": 0,
        "cancelled": 0,
    }
    for t in all_trips:
        s = t.get("status")
        if s in status_counts:
            status_counts[s] += 1

    # MTD revenue: completed trips where completed_at >= first of month
    mtd_revenue = sum(
        (t.get("rate_total") or 0)
        for t in all_trips
        if t.get("completed_at") and t["completed_at"] >= mtd and t.get("rate_total")
    )

    # Active driver count
    active_drivers_res = (
        sb.table("light_vehicle_drivers")
        .select("id", count="exact")
        .eq("status", "active")
        .execute()
    )

    # Today's trips
    today_res = (
        sb.table("light_vehicle_trips")
        .select("id", count="exact")
        .gte("scheduled_at", today)
        .execute()
    )

    return {
        "trips_by_type": type_counts,
        "trips_by_status": status_counts,
        "total_trips": len(all_trips),
        "mtd_revenue": float(mtd_revenue),
        "active_drivers": active_drivers_res.count or 0,
        "todays_trips": today_res.count or 0,
    }


# ===========================================================================
# TRIPS — list, create, get, update, delete
# ===========================================================================

@router.get("/trips")
def list_trips(
    trip_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> dict:
    """List trips with optional filters by trip_type and/or status."""
    sb = get_supabase()
    q = (
        sb.table("light_vehicle_trips")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if trip_type:
        q = q.eq("trip_type", trip_type)
    if status:
        q = q.eq("status", status)
    res = q.execute()
    items = res.data or []
    return {"items": items, "total": len(items)}


@router.post("/trips")
def create_trip(payload: dict) -> dict:
    """
    Create a new light-fleet trip.

    Required fields: trip_type, pickup_address, dropoff_address.
    All other columns are optional and passed through as-is.
    """
    required = {"trip_type", "pickup_address", "dropoff_address"}
    missing = required - payload.keys()
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing required fields: {missing}")

    payload.setdefault("status", "pending")
    payload.setdefault("created_at", _now_iso())
    payload.setdefault("updated_at", _now_iso())

    res = get_supabase().table("light_vehicle_trips").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Trip creation failed")
    return {"ok": True, "item": res.data[0]}


@router.get("/trips/{trip_id}")
def get_trip(trip_id: str) -> dict:
    """Fetch a single trip record by ID."""
    sb = get_supabase()
    return _require_trip(sb, trip_id)


@router.patch("/trips/{trip_id}")
def update_trip(trip_id: str, payload: dict) -> dict:
    """
    Update a trip.  Accepted fields include:
    status, driver_id, notes, dispatcher_notes, pod_url,
    rate_total, rate_per_mile, estimated_miles,
    completed_at, started_at, scheduled_at, and any other column.
    """
    payload["updated_at"] = _now_iso()
    sb = get_supabase()
    _require_trip(sb, trip_id)  # 404 guard
    res = sb.table("light_vehicle_trips").update(payload).eq("id", trip_id).execute()
    return {"ok": True, "item": res.data[0] if res.data else {}}


@router.delete("/trips/{trip_id}", response_model=None, status_code=204)
def delete_trip(trip_id: str) -> Response:
    """Hard-delete a trip record."""
    sb = get_supabase()
    _require_trip(sb, trip_id)  # 404 guard
    sb.table("light_vehicle_trips").delete().eq("id", trip_id).execute()
    return Response(status_code=204)


# ===========================================================================
# DRIVER ASSIGNMENT — assign, start, complete
# ===========================================================================

@router.post("/trips/{trip_id}/assign")
def assign_driver(trip_id: str, payload: dict) -> dict:
    """
    Assign a driver to a trip.

    Body: { "driver_id": "<uuid>" }

    Sets driver_id and transitions status → assigned.
    """
    driver_id = payload.get("driver_id")
    if not driver_id:
        raise HTTPException(status_code=422, detail="driver_id is required")

    sb = get_supabase()
    trip = _require_trip(sb, trip_id)

    if trip["status"] not in ("pending", "assigned"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot assign driver to a trip with status '{trip['status']}'",
        )

    # Verify driver exists and is active
    drv_res = sb.table("light_vehicle_drivers").select("id,status").eq("id", driver_id).execute()
    if not drv_res.data:
        raise HTTPException(status_code=404, detail="Driver not found")
    if drv_res.data[0].get("status") != "active":
        raise HTTPException(status_code=409, detail="Driver is not active")

    update = {
        "driver_id": driver_id,
        "status": "assigned",
        "updated_at": _now_iso(),
    }
    res = sb.table("light_vehicle_trips").update(update).eq("id", trip_id).execute()
    try:
        from ..triggers import fire_lf_trip_booked
        fire_lf_trip_booked(str(trip_id))
    except Exception:
        pass
    return {"ok": True, "item": res.data[0] if res.data else {}}


@router.post("/trips/{trip_id}/start")
def start_trip(trip_id: str) -> dict:
    """
    Mark a trip as started (driver en route / picked up passenger).

    Transitions status → in_progress and sets started_at.
    """
    sb = get_supabase()
    trip = _require_trip(sb, trip_id)

    if trip["status"] != "assigned":
        raise HTTPException(
            status_code=409,
            detail=f"Trip must be in 'assigned' status to start (current: '{trip['status']}')",
        )

    update = {
        "status": "in_progress",
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    res = sb.table("light_vehicle_trips").update(update).eq("id", trip_id).execute()
    try:
        from ..triggers import fire_lf_trip_started
        fire_lf_trip_started(str(trip_id))
    except Exception:
        pass
    return {"ok": True, "item": res.data[0] if res.data else {}}


@router.post("/trips/{trip_id}/complete")
def complete_trip(trip_id: str, payload: dict | None = None) -> dict:
    """
    Mark a trip as completed.

    Transitions status → completed and sets completed_at.
    Optional body: { "pod_url": "...", "rate_total": 0.00 }
    """
    sb = get_supabase()
    trip = _require_trip(sb, trip_id)

    if trip["status"] != "in_progress":
        raise HTTPException(
            status_code=409,
            detail=f"Trip must be in 'in_progress' status to complete (current: '{trip['status']}')",
        )

    update: dict = {
        "status": "completed",
        "completed_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    if payload:
        if "pod_url" in payload:
            update["pod_url"] = payload["pod_url"]
        if "rate_total" in payload:
            update["rate_total"] = payload["rate_total"]

    res = sb.table("light_vehicle_trips").update(update).eq("id", trip_id).execute()
    try:
        from ..triggers import fire_lf_trip_completed
        fire_lf_trip_completed(str(trip_id))
    except Exception:
        pass

    # Increment driver total_trips counter
    driver_id = trip.get("driver_id")
    if driver_id:
        drv_res = sb.table("light_vehicle_drivers").select("total_trips").eq("id", driver_id).execute()
        if drv_res.data:
            current = drv_res.data[0].get("total_trips") or 0
            sb.table("light_vehicle_drivers").update(
                {"total_trips": current + 1, "updated_at": _now_iso()}
            ).eq("id", driver_id).execute()

    return {"ok": True, "item": res.data[0] if res.data else {}}


# ===========================================================================
# LIGHT VEHICLE DRIVERS
# ===========================================================================

@router.get("/drivers")
def list_drivers(
    status: str | None = None,
    vehicle_type: str | None = None,
    limit: int = 100,
) -> dict:
    """List light-vehicle drivers with optional status/vehicle_type filters."""
    sb = get_supabase()
    q = (
        sb.table("light_vehicle_drivers")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        q = q.eq("status", status)
    if vehicle_type:
        q = q.eq("vehicle_type", vehicle_type)
    res = q.execute()
    items = res.data or []
    return {"items": items, "total": len(items)}


@router.post("/drivers")
def create_driver(payload: dict) -> dict:
    """
    Create a new light-vehicle driver record.

    Required: name.
    All compliance fields (mvr_status, background_check_status) default to 'pending'.
    """
    if not payload.get("name"):
        raise HTTPException(status_code=422, detail="Driver name is required")

    payload.setdefault("status", "active")
    payload.setdefault("mvr_status", "pending")
    payload.setdefault("background_check_status", "pending")
    payload.setdefault("total_trips", 0)
    payload.setdefault("approved_services", [])
    payload.setdefault("created_at", _now_iso())
    payload.setdefault("updated_at", _now_iso())

    # Normalise and store phone_e164 if a phone was supplied
    raw_phone = payload.get("phone") or payload.get("phone_e164") or ""
    phone_e164: str | None = None
    if raw_phone:
        try:
            phone_e164 = normalize_phone(raw_phone)
            payload["phone"]       = phone_e164
            payload["phone_e164"]  = phone_e164
        except ValueError:
            pass  # store as-is if format is unexpected

    res = get_supabase().table("light_vehicle_drivers").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Driver creation failed")

    driver = res.data[0]

    # Fire onboarding automation
    try:
        from ..triggers import fire_lf_driver_onboarding
        fire_lf_driver_onboarding(str(driver["id"]))
    except Exception:
        pass

    # Send Falcon Light Fleet welcome SMS
    if phone_e164:
        _send_falcon_lf_welcome(phone_e164, driver.get("name") or "")

    return {"ok": True, "item": driver}


@router.patch("/drivers/{driver_id}")
def update_driver(driver_id: str, payload: dict) -> dict:
    """
    Update a driver record.

    Common updates: status, mvr_status, mvr_checked_at, background_check_status,
    rating, approved_services, vehicle_type, vehicle_plate,
    vehicle_insurance_expires, license_expires.
    """
    payload["updated_at"] = _now_iso()
    sb = get_supabase()
    res = sb.table("light_vehicle_drivers").select("id").eq("id", driver_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Driver not found")
    upd = sb.table("light_vehicle_drivers").update(payload).eq("id", driver_id).execute()
    return {"ok": True, "item": upd.data[0] if upd.data else {}}


@router.delete("/drivers/{driver_id}", response_model=None, status_code=204)
def delete_driver(driver_id: str) -> Response:
    """Hard-delete a driver record."""
    sb = get_supabase()
    res = sb.table("light_vehicle_drivers").select("id").eq("id", driver_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Driver not found")
    sb.table("light_vehicle_drivers").delete().eq("id", driver_id).execute()
    return Response(status_code=204)


# ===========================================================================
# NEMT CLIENTS
# ===========================================================================

@router.get("/nemt/clients")
def list_nemt_clients(
    status: str | None = None,
    limit: int = 100,
) -> dict:
    """List NEMT patient/client records."""
    sb = get_supabase()
    q = (
        sb.table("nemt_clients")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        q = q.eq("status", status)
    res = q.execute()
    items = res.data or []
    return {"items": items, "total": len(items)}


@router.post("/nemt/clients")
def create_nemt_client(payload: dict) -> dict:
    """
    Create a new NEMT client (repeat medical transport patient).

    Required: name.
    """
    if not payload.get("name"):
        raise HTTPException(status_code=422, detail="Client name is required")

    payload.setdefault("status", "active")
    payload.setdefault("total_trips", 0)
    payload.setdefault("created_at", _now_iso())

    res = get_supabase().table("nemt_clients").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="NEMT client creation failed")
    return {"ok": True, "item": res.data[0]}


@router.patch("/nemt/clients/{client_id}")
def update_nemt_client(client_id: str, payload: dict) -> dict:
    """
    Update a NEMT client record.

    Common updates: name, phone, address, insurance_provider, insurance_id,
    mobility_needs, notes, status.
    """
    sb = get_supabase()
    res = sb.table("nemt_clients").select("id").eq("id", client_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="NEMT client not found")
    upd = sb.table("nemt_clients").update(payload).eq("id", client_id).execute()
    return {"ok": True, "item": upd.data[0] if upd.data else {}}


# ===========================================================================
# EXECUTIVE ACCOUNTS
# ===========================================================================

@router.get("/executive/accounts")
def list_executive_accounts(
    status: str | None = None,
    limit: int = 100,
) -> dict:
    """List corporate executive-transport account records."""
    sb = get_supabase()
    q = (
        sb.table("executive_accounts")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        q = q.eq("status", status)
    res = q.execute()
    items = res.data or []
    return {"items": items, "total": len(items)}


@router.post("/executive/accounts")
def create_executive_account(payload: dict) -> dict:
    """
    Create a new executive-transport corporate account.

    Required: company_name.
    """
    if not payload.get("company_name"):
        raise HTTPException(status_code=422, detail="company_name is required")

    payload.setdefault("status", "active")
    payload.setdefault("billing_type", "invoice")
    payload.setdefault("total_trips", 0)
    payload.setdefault("created_at", _now_iso())

    res = get_supabase().table("executive_accounts").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Executive account creation failed")
    return {"ok": True, "item": res.data[0]}


@router.patch("/executive/accounts/{account_id}")
def update_executive_account(account_id: str, payload: dict) -> dict:
    """
    Update an executive account.

    Common updates: company_name, contact_name, contact_phone, contact_email,
    billing_type, rate_per_mile, flat_rate_airport, contract_expires, status.
    """
    sb = get_supabase()
    res = sb.table("executive_accounts").select("id").eq("id", account_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Executive account not found")
    upd = sb.table("executive_accounts").update(payload).eq("id", account_id).execute()
    return {"ok": True, "item": upd.data[0] if upd.data else {}}


# ===========================================================================
# SELF-SERVICE DRIVER INTAKE (public — no auth)
# ===========================================================================

@public_router.post("/drivers/intake")
def driver_intake(payload: dict) -> dict:
    """
    Self-service driver signup endpoint — called from website.html signup form.

    Passes the submission through Maya (intake agent) for instant evaluation.
    Clean record + active insurance → approved immediately and driver row created.
    Dirty record → denied with reason, no row created.
    """
    from ..agents import maya
    result = maya.run({**payload, "action": "process_intake"})
    if not result.get("approved"):
        reason = result.get("reason", "requirements_not_met")
        status_msg = {
            "dirty_record": "A clean driving record is required to join 3 Lakes Light Fleet.",
            "no_insurance": "Active vehicle insurance is required before activation.",
            "missing_required_fields": "Please fill in all required fields.",
        }.get(reason, "Your application could not be processed at this time.")
        raise HTTPException(status_code=422, detail=status_msg)
    return {
        "ok": True,
        "status": result.get("status", "pending_verification"),
        "driver_id": result.get("driver_id"),
        "verification_url": result.get("verification_url"),
        "message": result.get("message", "Check your phone for next steps."),
    }


@public_router.get("/drivers/{driver_id}/compliance-status")
def public_driver_compliance(driver_id: str) -> dict:
    """
    Public compliance status for a light fleet driver by their driver_id.
    No auth required — drivers access via their own ID.
    """
    from ..agents import compliance_autopilot
    return compliance_autopilot.get_compliance_status(driver_id)


# ===========================================================================
# DRIVER EARNINGS, COMPLIANCE & INSTANT PAY
# ===========================================================================

@router.get("/drivers/{driver_id}/earnings")
def get_driver_earnings(driver_id: str, period: str = "week") -> dict:
    """Get aggregated earnings for a light fleet driver across all platforms."""
    from ..agents import earnings_aggregator
    return {
        "driver_id": driver_id,
        "period": period,
        "summary": earnings_aggregator.get_earnings(driver_id, period),
        "breakdown": earnings_aggregator.get_platform_breakdown(driver_id, period),
        "trend": earnings_aggregator.get_weekly_trend(driver_id),
    }


@router.get("/drivers/{driver_id}/compliance")
def get_driver_compliance(driver_id: str) -> dict:
    """Get compliance status for a light fleet driver."""
    from ..agents import compliance_autopilot
    return compliance_autopilot.get_compliance_status(driver_id)


@router.post("/drivers/{driver_id}/instant-pay")
def request_instant_pay(driver_id: str, payload: dict) -> dict:
    """
    Request instant/same-day payout for a driver's pending earnings.
    Deducts a 1.5% instant pay fee.
    Body: { "amount": float }
    """
    amount = float(payload.get("amount", 0))
    if amount <= 0:
        raise HTTPException(status_code=422, detail="amount must be positive")
    fee = round(amount * 0.015, 2)
    net = round(amount - fee, 2)
    # Log to atomic_ledger
    sb = get_supabase()
    sb.table("atomic_ledger").insert({
        "event_type": "instant_pay_requested",
        "event_source": "light_fleet.instant_pay",
        "logistics_payload": {"driver_id": driver_id},
        "financial_payload": {"gross": amount, "fee": fee, "net": net},
        "compliance_payload": {},
        "created_at": _now_iso(),
    }).execute()
    return {"ok": True, "driver_id": driver_id, "gross": amount, "fee": fee, "net": net, "status": "processing"}


# ===========================================================================
# LIVE GPS — Light Fleet Map
# ===========================================================================

@public_router.post("/driver-ping")
def driver_ping(payload: dict) -> dict:
    """
    Driver PWA posts GPS location. Updates last_lat/last_lng/last_ping_at on
    the driver record so Eagle Eye can show real-time positions on the LF Map.
    Body: { "driver_id": str, "lat": float, "lng": float, "trip_id": str|null }
    """
    driver_id = payload.get("driver_id")
    lat = payload.get("lat")
    lng = payload.get("lng")
    trip_id = payload.get("trip_id")

    if not driver_id or lat is None or lng is None:
        raise HTTPException(status_code=422, detail="driver_id, lat, lng required")

    sb = get_supabase()
    sb.table("light_vehicle_drivers").update({
        "last_lat": float(lat),
        "last_lng": float(lng),
        "last_ping_at": _now_iso(),
    }).eq("id", driver_id).execute()

    if trip_id:
        sb.table("light_vehicle_trips").update({
            "current_lat": float(lat),
            "current_lng": float(lng),
        }).eq("id", trip_id).execute()

    return {"ok": True}


@router.get("/live-locations")
def live_locations() -> dict:
    """
    Return active light fleet trips joined with driver GPS location.
    Used by Eagle Eye Light Fleet Map to place car markers on the map.
    """
    sb = get_supabase()
    trips_res = sb.table("light_vehicle_trips").select(
        "id,trip_type,status,pickup_address,dropoff_address,"
        "driver_id,passenger_name,rate_total,current_lat,current_lng"
    ).in_("status", ["assigned", "en_route", "arrived", "in_progress"]).execute()

    trips = trips_res.data or []
    driver_ids = list({t["driver_id"] for t in trips if t.get("driver_id")})

    drivers_by_id: dict = {}
    if driver_ids:
        drv_res = sb.table("light_vehicle_drivers").select(
            "id,full_name,vehicle_type,vehicle_plate,last_lat,last_lng,last_ping_at"
        ).in_("id", driver_ids).execute()
        for d in (drv_res.data or []):
            drivers_by_id[d["id"]] = d

    items = []
    for t in trips:
        drv = drivers_by_id.get(t.get("driver_id") or "", {})
        # Prefer trip-level position (fresher), fall back to driver last-ping
        lat = t.get("current_lat") or drv.get("last_lat")
        lng = t.get("current_lng") or drv.get("last_lng")
        if lat is None or lng is None:
            continue
        items.append({
            "trip_id": t["id"],
            "trip_type": t.get("trip_type", "gig"),
            "status": t.get("status"),
            "pickup_address": t.get("pickup_address"),
            "dropoff_address": t.get("dropoff_address"),
            "passenger_name": t.get("passenger_name"),
            "rate_total": t.get("rate_total"),
            "driver_id": drv.get("id"),
            "driver_name": drv.get("full_name"),
            "vehicle_type": drv.get("vehicle_type"),
            "vehicle_plate": drv.get("vehicle_plate"),
            "last_ping_at": drv.get("last_ping_at"),
            "lat": lat,
            "lng": lng,
        })

    return {"items": items, "total": len(items)}

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

router = APIRouter(dependencies=[Depends(require_bearer)])


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

    res = get_supabase().table("light_vehicle_drivers").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Driver creation failed")
    return {"ok": True, "item": res.data[0]}


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

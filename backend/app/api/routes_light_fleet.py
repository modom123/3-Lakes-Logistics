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


def _default_services(vehicle_type: str | None) -> list[str]:
    """Pick a sensible default segment so a driver is never invisible on every
    roster. Luxury vehicles default to executive; everything else to courier
    (the most general same-day segment)."""
    if (vehicle_type or "").lower() == "luxury":
        return ["executive"]
    return ["courier"]


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
    service: str | None = None,
    limit: int = 100,
) -> dict:
    """List light-vehicle drivers with optional status/vehicle_type/service filters."""
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
    if service:
        q = q.contains("approved_services", [service])
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
    payload.setdefault("created_at", _now_iso())
    payload.setdefault("updated_at", _now_iso())

    # Guarantee the driver is visible on at least one segment roster.
    # An empty approved_services means the ?service= filter hides them everywhere,
    # so derive a sensible default from vehicle_type.
    if not payload.get("approved_services"):
        payload["approved_services"] = _default_services(payload.get("vehicle_type"))

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


@router.get("/drivers/{driver_id}/agent-card")
def get_driver_agent_card(driver_id: str) -> dict:
    """
    Return a structured agent card for a driver — everything an AI agent needs
    to search load boards and match/accept loads on behalf of the driver.
    """
    sb = get_supabase()
    res = sb.table("light_vehicle_drivers").select("*").eq("id", driver_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Driver not found")
    d = res.data[0]

    card = {
        "driver_id":           d["id"],
        "name":                f"{d.get('first_name','')} {d.get('last_name','')}".strip(),
        "status":              d.get("status"),
        "hunt_enabled":        bool(d.get("hunt_enabled", False)),
        "vehicle": {
            "type":            d.get("vehicle_type"),
            "make":            d.get("vehicle_make"),
            "model":           d.get("vehicle_model"),
            "year":            d.get("vehicle_year"),
            "cargo_type":      d.get("vehicle_cargo_type"),
            "capacity_lbs":    d.get("vehicle_capacity_lbs"),
            "max_length_ft":   float(d["vehicle_max_length_ft"]) if d.get("vehicle_max_length_ft") else None,
        },
        "rates": {
            "min_rpm":          float(d["min_rpm"]) if d.get("min_rpm") else 1.50,
            "min_rate_total":   float(d["min_rate_total"]) if d.get("min_rate_total") else 25.00,
            "auto_accept_threshold": float(d["auto_accept_threshold"]) if d.get("auto_accept_threshold") else None,
        },
        "routing": {
            "max_deadhead_mi": d.get("max_deadhead_mi") or 50,
            "max_trip_miles":  d.get("max_trip_miles") or 300,
            "service_areas":   d.get("service_areas") or [],
        },
        "preferences": {
            "preferred_load_types": d.get("preferred_load_types") or [],
            "available_days":       d.get("available_days") or ["mon","tue","wed","thu","fri","sat"],
            "hours_start":          d.get("hours_start") or "07:00",
            "hours_end":            d.get("hours_end") or "20:00",
        },
        "stats": {
            "total_trips":       d.get("total_trips") or 0,
            "rating":            float(d["rating"]) if d.get("rating") else None,
            "matched_loads_count": d.get("matched_loads_count") or 0,
            "last_hunted_at":    d.get("last_hunted_at"),
        },
    }
    return {"ok": True, "card": card}


@router.post("/drivers/{driver_id}/hunt")
def hunt_for_driver(driver_id: str, payload: dict | None = None) -> dict:
    """
    Trigger a load-board hunt specifically for this driver.
    Uses the driver's agent card fields (min_rpm, max_deadhead_mi, vehicle type,
    service_areas) as search params.  Stores results tagged with driver_id.
    """
    from ..agents.load_hunter import hunt_for_driver as _hunt

    result = _hunt(driver_id, overrides=payload or {})
    return result


# ===========================================================================
# LOAD HUNT RESULTS
# ===========================================================================

@router.get("/loads/matched")
def list_matched_loads(
    driver_id: str | None = None,
    limit: int = 50,
    is_hot: bool | None = None,
) -> dict:
    """
    Fetch load_hunter_results, optionally filtered by driver_id and/or is_hot.
    """
    sb = get_supabase()
    q = (
        sb.table("load_hunter_results")
        .select("*")
        .order("found_at", desc=True)
        .limit(limit)
    )
    if driver_id:
        q = q.eq("driver_id", driver_id)
    if is_hot is not None:
        q = q.eq("is_hot", is_hot)
    rows = q.execute().data or []
    return {"loads": rows, "total": len(rows)}


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
    """Update a NEMT client record."""
    sb = get_supabase()
    res = sb.table("nemt_clients").select("id").eq("id", client_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="NEMT client not found")
    upd = sb.table("nemt_clients").update(payload).eq("id", client_id).execute()
    return {"ok": True, "item": upd.data[0] if upd.data else {}}


# ===========================================================================
# NEMT RECURRING SCHEDULES
# ===========================================================================

@router.get("/nemt/schedules")
def list_nemt_schedules(status: str | None = None, client_id: str | None = None,
                        limit: int = 100) -> dict:
    """List recurring NEMT trip schedules."""
    sb = get_supabase()
    q = sb.table("nemt_recurring_schedules").select("*, nemt_clients(name,phone,insurance_id)").order(
        "created_at", desc=True).limit(limit)
    if status:
        q = q.eq("status", status)
    if client_id:
        q = q.eq("nemt_client_id", client_id)
    return {"items": q.execute().data or [], "total": 0}


@router.post("/nemt/schedules")
def create_nemt_schedule(payload: dict) -> dict:
    """Create a recurring NEMT schedule for a patient.

    Required: nemt_client_id, frequency, days_of_week (for weekly/biweekly),
              time_of_day (HH:MM), pickup_address, dropoff_address.
    frequency: daily | weekly | biweekly | monthly
    """
    required = ("nemt_client_id", "frequency", "time_of_day", "pickup_address", "dropoff_address")
    missing = [f for f in required if not payload.get(f)]
    if missing:
        raise HTTPException(status_code=422, detail=f"missing required fields: {missing}")

    payload.setdefault("status", "active")
    payload.setdefault("effective_from", _today_iso()[:10])
    payload.setdefault("created_at", _now_iso())
    payload.setdefault("updated_at", _now_iso())

    res = get_supabase().table("nemt_recurring_schedules").insert(payload).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="schedule creation failed")
    return {"ok": True, "item": res.data[0]}


@router.patch("/nemt/schedules/{schedule_id}")
def update_nemt_schedule(schedule_id: str, payload: dict) -> dict:
    """Update schedule (pause/resume, change time, update auth number)."""
    sb = get_supabase()
    if not sb.table("nemt_recurring_schedules").select("id").eq("id", schedule_id).execute().data:
        raise HTTPException(status_code=404, detail="schedule not found")
    payload["updated_at"] = _now_iso()
    res = sb.table("nemt_recurring_schedules").update(payload).eq("id", schedule_id).execute()
    return {"ok": True, "item": res.data[0] if res.data else {}}


@router.post("/nemt/schedules/generate-trips")
def generate_scheduled_trips(payload: dict | None = None) -> dict:
    """Generate upcoming trips from all active recurring schedules.

    Looks ahead 7 days (or 'days_ahead' in payload) and creates
    light_vehicle_trips rows for any schedule that doesn't already have
    a trip on that day.  Safe to call multiple times — idempotent on
    (schedule_id, date).

    Run daily via cron or manually.
    """
    from datetime import date, timedelta, time as dt_time
    import pytz

    sb       = get_supabase()
    p        = payload or {}
    days_ahead = int(p.get("days_ahead", 7))
    today    = date.today()

    # Load all active schedules
    schedules = sb.table("nemt_recurring_schedules").select(
        "*, nemt_clients(name,phone,insurance_provider,insurance_id,dob,mobility_needs)"
    ).eq("status", "active").execute().data or []

    created  = 0
    skipped  = 0
    errors   = 0
    detail: list[dict] = []

    DOW_NAMES = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]

    for sched in schedules:
        sched_id    = sched["id"]
        freq        = sched["frequency"]
        dow_list    = sched.get("days_of_week") or []
        time_str    = sched.get("time_of_day") or "09:00"
        eff_from    = date.fromisoformat(sched["effective_from"])
        eff_until   = date.fromisoformat(sched["effective_until"]) if sched.get("effective_until") else None
        client      = sched.get("nemt_clients") or {}

        # Build candidate dates in the look-ahead window
        for offset in range(days_ahead + 1):
            target_date = today + timedelta(days=offset)

            if target_date < eff_from:
                continue
            if eff_until and target_date > eff_until:
                continue

            # Check recurrence pattern
            dow = target_date.weekday()  # Mon=0 … Sun=6 in Python
            py_to_js_dow = (dow + 1) % 7  # convert to Sun=0 JS convention
            match = False
            if freq == "daily":
                match = True
            elif freq in ("weekly", "biweekly"):
                if py_to_js_dow in (dow_list or []):
                    if freq == "weekly":
                        match = True
                    else:  # biweekly — every other week from effective_from
                        weeks_since = (target_date - eff_from).days // 7
                        match = (weeks_since % 2 == 0)
            elif freq == "monthly":
                # Same day-of-month as effective_from
                match = (target_date.day == eff_from.day)

            if not match:
                continue

            # Build scheduled_at timestamp
            try:
                tz_name = sched.get("timezone") or "America/Los_Angeles"
                tz      = pytz.timezone(tz_name)
                h, m    = [int(x) for x in str(time_str)[:5].split(":")]
                local_dt = tz.localize(datetime(target_date.year, target_date.month,
                                               target_date.day, h, m))
                scheduled_at_iso = local_dt.isoformat()
            except Exception:
                scheduled_at_iso = f"{target_date.isoformat()}T{time_str[:5]}:00-07:00"

            # Idempotency check — skip if trip already exists for this schedule+date
            date_str = target_date.isoformat()
            existing = sb.table("light_vehicle_trips").select("id").eq(
                "notes", f"recurring:{sched_id}:{date_str}"
            ).execute().data
            if existing:
                skipped += 1
                continue

            # Create the trip
            trip_row = {
                "trip_type":            "nemt",
                "status":               "pending",
                "passenger_name":       client.get("name") or "",
                "passenger_phone":      client.get("phone") or "",
                "nemt_client_id":       sched["nemt_client_id"],
                "pickup_address":       sched["pickup_address"],
                "dropoff_address":      sched["dropoff_address"],
                "scheduled_at":         scheduled_at_iso,
                "insurance_provider":   sched.get("insurance_provider") or client.get("insurance_provider") or "",
                "insurance_auth_number":sched.get("insurance_auth_number") or "",
                "mobility_needs":       sched.get("mobility_needs") or client.get("mobility_needs") or "",
                "vehicle_class":        sched.get("vehicle_class") or "",
                "notes":                f"recurring:{sched_id}:{date_str}",
                "dispatcher_notes":     f"Auto-generated from recurring schedule {sched_id[:8]}",
            }
            try:
                sb.table("light_vehicle_trips").insert(trip_row).execute()
                # Update last_generated_date + total_generated
                sb.table("nemt_recurring_schedules").update({
                    "last_generated_date": date_str,
                    "total_generated":     (sched.get("total_generated") or 0) + 1,
                    "updated_at":          _now_iso(),
                }).eq("id", sched_id).execute()
                created += 1
                detail.append({"schedule_id": sched_id, "date": date_str, "status": "created"})
            except Exception as e:
                errors += 1
                detail.append({"schedule_id": sched_id, "date": date_str, "status": "error", "reason": str(e)[:100]})

    return {
        "ok":      True,
        "created": created,
        "skipped": skipped,
        "errors":  errors,
        "detail":  detail[:50],  # cap to keep response small
    }


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
    driver_id = result.get("driver_id")
    if not driver_id:
        db_err = result.get("db_error", "unknown — check Render logs")
        raise HTTPException(status_code=500, detail=f"Driver record not created: {db_err}")
    try:
        from ..triggers import fire_lf_driver_onboarding
        fire_lf_driver_onboarding(str(driver_id))
    except Exception:
        pass
    return {
        "ok": True,
        "status": result.get("status", "pending_verification"),
        "driver_id": driver_id,
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


@router.get("/compliance/alerts")
def list_compliance_alerts(resolved: bool | None = None, limit: int = 100) -> dict:
    """List LF compliance alerts — used by Eagle Eye Compliance tab."""
    sb = get_supabase()
    q = sb.table("lf_compliance_alerts").select("*").order("created_at", desc=True).limit(limit)
    if resolved is not None:
        q = q.eq("resolved", resolved)
    items = q.execute().data or []
    return {"items": items, "total": len(items)}


@router.patch("/compliance/alerts/{alert_id}/resolve")
def resolve_compliance_alert(alert_id: str) -> dict:
    """Mark a compliance alert as resolved (e.g. driver renewed their license)."""
    from datetime import datetime, timezone
    get_supabase().table("lf_compliance_alerts").update({
        "resolved": True, "resolved_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", alert_id).execute()
    return {"ok": True, "alert_id": alert_id}


@router.post("/compliance/sweep")
def trigger_compliance_sweep() -> dict:
    """Manually trigger the compliance sweep (normally runs daily at 06:15 UTC)."""
    from ..agents.compliance_autopilot import check_all_active_drivers
    result = check_all_active_drivers()
    return {"ok": True, **result}


@router.get("/billing/nemt/claims")
def list_nemt_claims(
    status: str | None = None,
    limit: int = 100,
) -> dict:
    """List NEMT billing claims with optional status filter."""
    sb = get_supabase()
    q = sb.table("nemt_billing_claims").select("*").order("created_at", desc=True).limit(limit)
    if status:
        q = q.eq("status", status)
    res = q.execute()
    items = res.data or []
    return {"items": items, "total": len(items)}


@router.post("/billing/corporate/setup-account/{account_id}")
def setup_corporate_stripe_account(account_id: str) -> dict:
    """Create a Stripe Customer for a corporate executive account if not already set up."""
    from ..settings import get_settings
    import stripe as _stripe
    s = get_settings()
    if not s.stripe_secret_key:
        raise HTTPException(status_code=503, detail="stripe not configured")
    _stripe.api_key = s.stripe_secret_key

    sb = get_supabase()
    acct = sb.table("executive_accounts").select(
        "id,company_name,contact_email,invoice_email,stripe_customer_id"
    ).eq("id", account_id).maybe_single().execute().data
    if not acct:
        raise HTTPException(status_code=404, detail="executive account not found")

    if acct.get("stripe_customer_id"):
        return {"ok": True, "stripe_customer_id": acct["stripe_customer_id"], "note": "already set up"}

    billing_email = acct.get("invoice_email") or acct.get("contact_email") or ""
    try:
        customer = _stripe.Customer.create(
            name=acct.get("company_name") or "",
            email=billing_email,
            metadata={"executive_account_id": account_id},
        )
        sb.table("executive_accounts").update({
            "stripe_customer_id": customer.id
        }).eq("id", account_id).execute()
        return {"ok": True, "stripe_customer_id": customer.id, "account_id": account_id}
    except _stripe.error.StripeError as e:
        raise HTTPException(status_code=502, detail=f"stripe error: {e.user_message or str(e)}")


@router.post("/billing/corporate/finalize-batch")
def finalize_corporate_invoices(payload: dict | None = None) -> dict:
    """Finalize pending Stripe Invoice drafts for weekly/monthly corporate accounts.

    Collects all pending InvoiceItems per customer, creates and finalizes a
    single Invoice per account.  Run at end of billing period.
    """
    from ..settings import get_settings
    import stripe as _stripe
    from datetime import datetime, timezone
    s = get_settings()
    if not s.stripe_secret_key:
        raise HTTPException(status_code=503, detail="stripe not configured")
    _stripe.api_key = s.stripe_secret_key

    p       = payload or {}
    cycle   = p.get("cycle") or "monthly"   # filter accounts by invoice_cycle
    now_iso = datetime.now(timezone.utc).isoformat()
    sb      = get_supabase()

    # Find all corporate accounts on this billing cycle with a Stripe Customer
    accounts = sb.table("executive_accounts").select(
        "id,company_name,stripe_customer_id,net_days,invoice_cycle"
    ).eq("status", "active").eq("invoice_cycle", cycle).execute().data or []

    invoiced = 0
    skipped  = 0
    results  = []

    for acct in accounts:
        cust_id = acct.get("stripe_customer_id")
        if not cust_id:
            skipped += 1
            continue

        try:
            # Check if there are any pending invoice items for this customer
            items = _stripe.InvoiceItem.list(customer=cust_id, pending=True, limit=100)
            if not items.data:
                skipped += 1
                continue

            net_days = int(acct.get("net_days") or 30)
            invoice = _stripe.Invoice.create(
                customer=cust_id,
                collection_method="send_invoice",
                days_until_due=net_days,
                auto_advance=True,
                metadata={"account_id": acct["id"], "cycle": cycle, "finalized_at": now_iso},
            )
            finalized = _stripe.Invoice.finalize_invoice(invoice.id)
            invoiced += 1
            results.append({
                "account_id":   acct["id"],
                "company":      acct.get("company_name"),
                "invoice_id":   finalized.id,
                "invoice_url":  finalized.hosted_invoice_url or "",
                "amount_due":   finalized.amount_due / 100,
                "status":       "sent",
            })
        except _stripe.error.StripeError as e:
            results.append({
                "account_id": acct["id"],
                "status":     "failed",
                "reason":     str(e.user_message or e)[:200],
            })

    return {
        "ok":           True,
        "invoiced":     invoiced,
        "skipped":      skipped,
        "cycle":        cycle,
        "finalized_at": now_iso,
        "detail":       results,
    }


@router.post("/billing/nemt/submit-batch")
def submit_nemt_billing_batch(payload: dict | None = None) -> dict:
    """Submit all queued NEMT billing claims to the configured clearinghouse.

    Supports Change Healthcare and Trizetto via HTTP.  When no clearinghouse
    credentials are configured, claims are marked 'submitted' with a manual
    reference so staff can submit them on the payer portal directly — the
    queue is still drained so claims don't pile up indefinitely.

    Payload (optional):
      clearinghouse  — 'change_healthcare' | 'trizetto' | 'manual' (default)
      limit          — max claims to process in one run (default 50)
    """
    from ..settings import get_settings
    from datetime import datetime, timezone
    import httpx

    s     = get_settings()
    sb    = get_supabase()
    now   = datetime.now(timezone.utc)
    p     = payload or {}
    limit = int(p.get("limit", 50))
    clearinghouse = p.get("clearinghouse") or getattr(s, "nemt_clearinghouse", None) or "manual"

    # Load queued claims
    queued = sb.table("nemt_billing_claims").select("*").eq("status", "queued").limit(limit).execute().data or []
    if not queued:
        return {"ok": True, "submitted": 0, "note": "no queued claims"}

    ch_url     = getattr(s, "nemt_clearinghouse_url", None)
    ch_api_key = getattr(s, "nemt_clearinghouse_api_key", None)

    results  = []
    submitted = 0
    failed    = 0

    for claim in queued:
        claim_id = claim["id"]
        ref = f"3LL-{claim_id[:8].upper()}"   # internal reference until clearinghouse assigns one

        if clearinghouse != "manual" and ch_url and ch_api_key:
            # ── Real clearinghouse submission ─────────────────────────────────
            # Build an 837P-style JSON payload (clearinghouse-agnostic structure;
            # Change Healthcare and Trizetto both accept similar JSON envelopes).
            body_837p = {
                "transactionType": "837P",
                "tradingPartner":   claim.get("payer_id") or "",
                "subscriber": {
                    "memberId":      claim.get("patient_medicaid_id") or "",
                    "firstName":     (claim.get("patient_name") or "").split(" ")[0],
                    "lastName":      (claim.get("patient_name") or "").split(" ")[-1],
                    "dateOfBirth":   str(claim.get("patient_dob") or ""),
                    "insuredId":     claim.get("insurance_member_id") or "",
                },
                "provider": {
                    "npi":           claim.get("provider_npi") or "",
                    "taxonomyCode":  claim.get("provider_taxonomy") or "341600000X",
                },
                "claim": {
                    "patientControlNumber": ref,
                    "authorizationNumber":  claim.get("insurance_auth_number") or "",
                    "dateOfService":        str(claim.get("date_of_service") or ""),
                    "placeOfService":       "41",   # 41 = Ambulance – Land (NEMT)
                    "billedAmount":         float(claim.get("billed_amount") or 0),
                    "serviceLines": [{
                        "procedureCode":    claim.get("procedure_code") or "A0130",
                        "procedureModifier":claim.get("procedure_modifier") or "",
                        "diagnosisCode":    claim.get("diagnosis_code") or "",
                        "serviceDate":      str(claim.get("date_of_service") or ""),
                        "units":            int(claim.get("units") or 1),
                        "chargeAmount":     float(claim.get("billed_amount") or 0),
                    }],
                    "origin": {
                        "address": claim.get("pickup_address") or "",
                    },
                    "destination": {
                        "address": claim.get("dropoff_address") or "",
                    },
                },
            }
            try:
                resp = httpx.post(
                    ch_url,
                    json=body_837p,
                    headers={"Authorization": f"Bearer {ch_api_key}",
                             "Content-Type": "application/json"},
                    timeout=15,
                )
                resp.raise_for_status()
                resp_json = resp.json()
                ref = resp_json.get("claimId") or resp_json.get("referenceNumber") or ref
                sb.table("nemt_billing_claims").update({
                    "status":         "submitted",
                    "clearinghouse":  clearinghouse,
                    "submission_ref": ref,
                    "submitted_at":   now.isoformat(),
                    "updated_at":     now.isoformat(),
                }).eq("id", claim_id).execute()
                results.append({"claim_id": claim_id, "status": "submitted", "ref": ref})
                submitted += 1
            except Exception as e:
                sb.table("nemt_billing_claims").update({
                    "rejection_reason": str(e)[:300],
                    "updated_at":       now.isoformat(),
                }).eq("id", claim_id).execute()
                results.append({"claim_id": claim_id, "status": "error", "reason": str(e)[:200]})
                failed += 1
        else:
            # ── Manual / no clearinghouse configured ──────────────────────────
            # Mark submitted with a 3LL reference so staff can enter on payer portal.
            sb.table("nemt_billing_claims").update({
                "status":         "submitted",
                "clearinghouse":  "manual",
                "submission_ref": ref,
                "submitted_at":   now.isoformat(),
                "updated_at":     now.isoformat(),
            }).eq("id", claim_id).execute()
            results.append({"claim_id": claim_id, "status": "submitted", "ref": ref, "mode": "manual"})
            submitted += 1

    return {
        "ok":          True,
        "submitted":   submitted,
        "failed":      failed,
        "clearinghouse": clearinghouse,
        "processed_at": now.isoformat(),
        "detail":      results,
    }


@router.patch("/billing/nemt/claims/{claim_id}")
def update_nemt_claim(claim_id: str, payload: dict) -> dict:
    """Update a billing claim — record payer response (accepted/rejected/paid)."""
    sb = get_supabase()
    res = sb.table("nemt_billing_claims").select("id").eq("id", claim_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="claim not found")

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    update = {**payload, "updated_at": now_iso}

    # Auto-stamp transition timestamps
    status = payload.get("status")
    if status == "accepted" and "accepted_at" not in update:
        update["accepted_at"] = now_iso
    elif status == "rejected" and "rejected_at" not in update:
        update["rejected_at"] = now_iso
    elif status == "paid" and "paid_at" not in update:
        update["paid_at"] = now_iso

    sb.table("nemt_billing_claims").update(update).eq("id", claim_id).execute()
    return {"ok": True, "claim_id": claim_id, "status": status}


@router.post("/payouts/weekly-batch")
def run_weekly_payout_batch(payload: dict | None = None) -> dict:
    """Process all queued driver earnings and send one Stripe Transfer per driver.

    Intended to run every Friday.  Aggregates all 'queued' rows in
    lf_driver_payouts, groups by driver, and fires a single Transfer per driver
    for the week's total.  Marks rows 'paid' on success.
    """
    from ..settings import get_settings
    import stripe as _stripe
    s = get_settings()
    if not s.stripe_secret_key:
        raise HTTPException(status_code=503, detail="stripe not configured")
    _stripe.api_key = s.stripe_secret_key

    from datetime import datetime, timezone
    sb = get_supabase()

    # Load all queued rows
    queued = sb.table("lf_driver_payouts").select(
        "id, driver_id, net_cents"
    ).eq("status", "queued").execute().data or []

    if not queued:
        return {"ok": True, "drivers_paid": 0, "total_transferred_usd": 0.0, "note": "no queued payouts"}

    # Group by driver
    from collections import defaultdict
    by_driver: dict[str, list] = defaultdict(list)
    for row in queued:
        by_driver[row["driver_id"]].append(row)

    # Fetch Stripe account IDs for all drivers in one query
    driver_ids = list(by_driver.keys())
    drv_rows = sb.table("light_vehicle_drivers").select(
        "id, stripe_account_id, stripe_account_status"
    ).in_("id", driver_ids).execute().data or []
    stripe_map = {
        d["id"]: d for d in drv_rows
        if d.get("stripe_account_status") == "connected" and d.get("stripe_account_id")
    }

    now_iso = datetime.now(timezone.utc).isoformat()
    results = []
    total_cents = 0

    for driver_id, rows in by_driver.items():
        drv = stripe_map.get(driver_id)
        if not drv:
            results.append({"driver_id": driver_id, "status": "skipped", "reason": "stripe_not_connected"})
            continue

        batch_cents = sum(r["net_cents"] for r in rows)
        if batch_cents <= 0:
            continue

        record_ids = [r["id"] for r in rows]
        stripe_account_id = drv["stripe_account_id"]

        try:
            transfer = _stripe.Transfer.create(
                amount=batch_cents,
                currency="usd",
                destination=stripe_account_id,
                metadata={
                    "driver_id":   driver_id,
                    "source":      "lf_weekly_batch",
                    "record_ids":  ",".join(str(x) for x in record_ids[:20]),
                    "week_ending": now_iso[:10],
                },
            )
            # Mark all contributing rows as paid
            sb.table("lf_driver_payouts").update({
                "status":             "paid",
                "stripe_transfer_id": transfer.id,
                "processed_at":       now_iso,
                "paid_at":            now_iso,
            }).in_("id", record_ids).execute()
            total_cents += batch_cents
            results.append({
                "driver_id":   driver_id,
                "status":      "paid",
                "net_usd":     round(batch_cents / 100, 2),
                "transfer_id": transfer.id,
                "trips":       len(rows),
            })
        except _stripe.error.StripeError as e:
            results.append({
                "driver_id": driver_id,
                "status":    "failed",
                "reason":    str(e.user_message or e)[:200],
            })

    paid_count = sum(1 for r in results if r["status"] == "paid")
    return {
        "ok":                    True,
        "drivers_paid":          paid_count,
        "drivers_skipped":       len(results) - paid_count,
        "total_transferred_usd": round(total_cents / 100, 2),
        "processed_at":          now_iso,
        "detail":                results,
    }


@router.post("/drivers/{driver_id}/instant-pay")
def request_instant_pay(driver_id: str, payload: dict) -> dict:
    """Admin-triggered instant payout for an LF driver.  0.75% processing fee."""
    amount = float(payload.get("amount", 0))
    if amount <= 0:
        raise HTTPException(status_code=422, detail="amount must be positive")

    _INSTANT_FEE_PCT = 0.0075
    fee       = round(amount * _INSTANT_FEE_PCT, 2)
    net       = round(amount - fee, 2)
    fee_cents = int(fee * 100)
    net_cents = int(net * 100)

    if net_cents <= 0:
        raise HTTPException(status_code=422, detail="amount too small after fee")

    sb = get_supabase()
    driver_row = sb.table("light_vehicle_drivers").select(
        "stripe_account_id, stripe_account_status"
    ).eq("id", driver_id).maybe_single().execute().data or {}

    if driver_row.get("stripe_account_status") != "connected":
        raise HTTPException(status_code=400, detail="driver Stripe account not connected")

    stripe_account_id = driver_row["stripe_account_id"]

    from ..settings import get_settings
    import stripe as _stripe
    s = get_settings()
    if not s.stripe_secret_key:
        raise HTTPException(status_code=503, detail="stripe not configured")
    _stripe.api_key = s.stripe_secret_key

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    payout_record_id = None
    try:
        rec = sb.table("lf_driver_payouts").insert({
            "driver_id":          driver_id,
            "payout_type":        "instant",
            "gross_cents":        int(amount * 100),
            "platform_fee_cents": 0,
            "instant_fee_cents":  fee_cents,
            "net_cents":          net_cents,
            "status":             "processing",
            "requested_at":       now.isoformat(),
        }).execute()
        payout_record_id = (rec.data or [{}])[0].get("id")

        transfer = _stripe.Transfer.create(
            amount=net_cents, currency="usd",
            destination=stripe_account_id,
            metadata={"driver_id": driver_id, "source": "admin_instant_pay"},
        )
        payout_id = None
        try:
            payout = _stripe.Payout.create(
                amount=net_cents, currency="usd", method="instant",
                stripe_account=stripe_account_id,
                metadata={"driver_id": driver_id, "transfer_id": transfer.id},
            )
            payout_id = payout.id
        except _stripe.error.StripeError:
            pass  # fall back to standard payout timing

        upd: dict = {"stripe_transfer_id": transfer.id, "processed_at": now.isoformat(),
                     "status": "paid" if payout_id else "processing"}
        if payout_id:
            upd["stripe_payout_id"] = payout_id
            upd["paid_at"] = now.isoformat()
        if payout_record_id:
            sb.table("lf_driver_payouts").update(upd).eq("id", payout_record_id).execute()

        return {"ok": True, "driver_id": driver_id, "gross": amount, "instant_fee": fee,
                "fee_pct": "0.75%", "net": net, "transfer_id": transfer.id,
                "payout_id": payout_id, "status": "paid" if payout_id else "processing"}

    except _stripe.error.StripeError as e:
        if payout_record_id:
            sb.table("lf_driver_payouts").update(
                {"status": "failed", "failure_reason": str(e)[:300]}
            ).eq("id", payout_record_id).execute()
        raise HTTPException(status_code=502, detail=f"stripe error: {e.user_message or str(e)}")


# ===========================================================================
# DRIVER PAYOUT ACCOUNT — Stripe Connect onboarding
# ===========================================================================

@router.post("/drivers/{driver_id}/payout-setup")
def lf_driver_payout_setup(driver_id: str) -> dict:
    """Create (or reuse) the driver's Stripe Connect payout account and return a
    fresh Stripe-hosted onboarding link.

    Used by Eagle Eye ('Resend payout link') and the driver PWA 'Set up payouts'
    button. Onboarding is idempotent — re-calling reuses the existing account and
    just mints a new link.
    """
    from ..payments import stripe_connect

    if not stripe_connect.is_configured():
        raise HTTPException(status_code=503, detail="stripe not configured")
    sb = get_supabase()
    drv = (
        sb.table("light_vehicle_drivers")
        .select("id,name,email,phone")
        .eq("id", driver_id)
        .maybe_single()
        .execute()
        .data
    )
    if not drv:
        raise HTTPException(status_code=404, detail="driver not found")

    account_id, url = stripe_connect.start_onboarding(
        "light_vehicle_drivers",
        driver_id,
        email=drv.get("email"),
        name=drv.get("name"),
        metadata={"segment": "light_fleet"},
    )
    if not url:
        raise HTTPException(status_code=502, detail="could not create onboarding link")
    return {"ok": True, "driver_id": driver_id, "account_id": account_id, "onboarding_url": url}


@router.get("/drivers/{driver_id}/payout-status")
def lf_driver_payout_status(driver_id: str) -> dict:
    """Return the driver's payout-account status, refreshed live from Stripe when
    a Connect account exists."""
    sb = get_supabase()
    drv = (
        sb.table("light_vehicle_drivers")
        .select(
            "id,stripe_account_id,stripe_account_status,"
            "stripe_payouts_enabled,stripe_onboarded_at"
        )
        .eq("id", driver_id)
        .maybe_single()
        .execute()
        .data
    )
    if not drv:
        raise HTTPException(status_code=404, detail="driver not found")

    account_id = drv.get("stripe_account_id")
    status = drv.get("stripe_account_status") or "not_connected"
    payouts_enabled = bool(drv.get("stripe_payouts_enabled"))

    if account_id:
        from ..payments import stripe_connect

        if stripe_connect.is_configured():
            synced = stripe_connect.sync_account_status(
                account_id, table="light_vehicle_drivers"
            )
            if synced.get("ok"):
                status = synced.get("status", status)
                payouts_enabled = bool(synced.get("payouts_enabled"))

    return {
        "driver_id": driver_id,
        "account_id": account_id,
        "status": status,
        "payouts_enabled": payouts_enabled,
        "can_receive_payouts": status == "connected",
        "onboarded_at": drv.get("stripe_onboarded_at"),
    }


# ===========================================================================
# LIVE GPS — Light Fleet Map
# ===========================================================================

@router.post("/trips/{trip_id}/tracking-link")
def create_tracking_link(trip_id: str) -> dict:
    """Generate a short-lived public tracking link for a passenger.

    Returns a URL the dispatcher/driver can SMS to the passenger.
    Link expires when the trip completes or after 24 hours, whichever comes first.
    """
    from datetime import timedelta
    sb  = get_supabase()
    trip = sb.table("light_vehicle_trips").select("id,status,passenger_phone").eq(
        "id", trip_id
    ).maybe_single().execute().data
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")
    if trip.get("status") in ("completed", "cancelled"):
        raise HTTPException(status_code=409, detail="trip is already complete")

    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    # Upsert so re-calling refreshes the token expiry
    existing = sb.table("lf_tracking_tokens").select("id,token").eq("trip_id", trip_id).execute().data
    if existing:
        token = existing[0]["token"]
        sb.table("lf_tracking_tokens").update({
            "expires_at": expires_at.isoformat(),
        }).eq("trip_id", trip_id).execute()
    else:
        rec = sb.table("lf_tracking_tokens").insert({
            "trip_id":    trip_id,
            "expires_at": expires_at.isoformat(),
        }).execute().data or [{}]
        token = rec[0].get("token", "")

    tracking_url = f"https://www.3lakeslogistics.com/track/{token}"
    return {
        "ok":          True,
        "trip_id":     trip_id,
        "tracking_url": tracking_url,
        "token":       token,
        "expires_at":  expires_at.isoformat(),
    }


@public_router.get("/track/{token}")
def get_trip_tracking(token: str) -> dict:
    """Public endpoint — returns live driver location for a trip.

    No auth required. Called by the passenger's tracking page
    (3lakeslogistics.com/track/{token}).
    """
    sb = get_supabase()

    # Look up token
    rec = sb.table("lf_tracking_tokens").select("trip_id, expires_at").eq("token", token).maybe_single().execute().data
    if not rec:
        raise HTTPException(status_code=404, detail="tracking link not found or expired")

    from datetime import datetime, timezone
    expires_at = datetime.fromisoformat(rec["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=410, detail="tracking link has expired")

    trip_id = rec["trip_id"]
    trip = sb.table("light_vehicle_trips").select(
        "id,trip_type,status,pickup_address,dropoff_address,passenger_name,"
        "scheduled_at,started_at,driver_id,current_lat,current_lng"
    ).eq("id", trip_id).maybe_single().execute().data or {}

    if trip.get("status") in ("completed", "cancelled"):
        return {
            "status":        trip["status"],
            "trip_id":       trip_id,
            "message":       "Your trip has been completed. Thank you for riding with 3 Lakes Light Fleet!",
        }

    # Get driver's last-known location
    driver_lat = trip.get("current_lat")
    driver_lng = trip.get("current_lng")
    driver_name = None
    last_ping   = None

    driver_id = trip.get("driver_id")
    if driver_id:
        drv = sb.table("light_vehicle_drivers").select(
            "name,last_lat,last_lng,last_ping_at"
        ).eq("id", str(driver_id)).maybe_single().execute().data or {}
        driver_name = drv.get("name")
        last_ping   = drv.get("last_ping_at")
        driver_lat  = driver_lat or drv.get("last_lat")
        driver_lng  = driver_lng or drv.get("last_lng")

    return {
        "trip_id":         trip_id,
        "status":          trip.get("status"),
        "trip_type":       trip.get("trip_type"),
        "pickup_address":  trip.get("pickup_address"),
        "dropoff_address": trip.get("dropoff_address"),
        "passenger_name":  trip.get("passenger_name"),
        "scheduled_at":    trip.get("scheduled_at"),
        "driver_name":     driver_name,
        "driver_lat":      driver_lat,
        "driver_lng":      driver_lng,
        "last_ping_at":    last_ping,
        "expires_at":      rec["expires_at"],
    }


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


@router.post("/route/optimize")
def optimize_route(payload: dict) -> dict:
    """Optimize stop order for a multi-stop Light Fleet trip.

    Body:
      origin       str  — driver start location or pickup address
      destination  str  — final dropoff
      waypoints    list[str] — intermediate stops in any order

    Returns the optimized stop sequence, per-leg distances/ETAs,
    total miles, and total estimated minutes.
    """
    origin      = payload.get("origin") or ""
    destination = payload.get("destination") or ""
    waypoints   = payload.get("waypoints") or []

    if not origin or not destination:
        raise HTTPException(status_code=422, detail="origin and destination required")
    if not isinstance(waypoints, list):
        raise HTTPException(status_code=422, detail="waypoints must be a list of address strings")

    from ..settings import get_settings
    s = get_settings()
    if not s.google_maps_api_key:
        raise HTTPException(status_code=503, detail="GOOGLE_MAPS_API_KEY not configured")

    from ..execution_engine.handlers.lf_dispatch import _optimize_route_via_google
    result = _optimize_route_via_google(origin, destination, waypoints, s.google_maps_api_key)
    if not result:
        raise HTTPException(status_code=502, detail="Google Maps route optimization failed")

    # Build human-readable ordered stop list
    ordered_stops = [origin]
    for idx in result.get("optimized_order", range(len(waypoints))):
        ordered_stops.append(waypoints[idx])
    ordered_stops.append(destination)

    return {
        "ok":               True,
        "total_miles":      result["total_miles"],
        "total_minutes":    result["total_minutes"],
        "stop_count":       len(ordered_stops),
        "ordered_stops":    ordered_stops,
        "optimized_order":  result["optimized_order"],
        "legs":             result["legs"],
    }


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
            "id,name,vehicle_type,vehicle_plate,last_lat,last_lng,last_ping_at"
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
            "driver_name": drv.get("name"),
            "vehicle_type": drv.get("vehicle_type"),
            "vehicle_plate": drv.get("vehicle_plate"),
            "last_ping_at": drv.get("last_ping_at"),
            "lat": lat,
            "lng": lng,
        })

    return {"items": items, "total": len(items)}

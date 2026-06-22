"""Driver endpoints — location tracking, documents, profile, loads, HOS, inspections."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Header, Depends, UploadFile, File, status
from pydantic import BaseModel

from ..supabase_client import get_supabase
from ..logging_service import get_logger
from .routes_driver_auth import require_driver_token

log = get_logger(__name__)
router = APIRouter(prefix="/driver", tags=["driver"])

DriverSession = Annotated[dict, Depends(require_driver_token)]


# ────────────────────────────────────────────────────────────────────────────
# MODELS
# ────────────────────────────────────────────────────────────────────────────

class LocationUpdate(BaseModel):
    driver_id: str
    lat: float
    lng: float
    accuracy: float | None = None
    speed_mph: float = 0
    heading: float | None = None
    ts: str


class DocumentUploadResponse(BaseModel):
    document_id: str
    url: str
    signed_url: str


# ────────────────────────────────────────────────────────────────────────────
# LOCATION TRACKING
# ────────────────────────────────────────────────────────────────────────────

@router.post("/location")
async def update_driver_location(req: LocationUpdate, session: DriverSession):
    """Driver sends real-time GPS location.

    Called every 30 seconds while driving. Updates truck_telemetry table.
    """
    driver_id = session["driver_id"]

    try:
        # Query driver to get carrier_id and truck_id
        result = get_supabase().table("drivers").select(
            "id, carrier_id"
        ).eq("id", driver_id).single().execute()

        driver = result.data
        carrier_id = driver["carrier_id"]

        # Get current load to extract truck_id
        load_result = get_supabase().table("loads").select(
            "id, truck_id"
        ).eq("driver_id", driver_id).eq("status", "in_transit").single().execute()

        truck_id = load_result.data.get("truck_id") if load_result.data else "unknown"

        # Insert/update telemetry
        get_supabase().table("truck_telemetry").insert({
            "carrier_id": carrier_id,
            "truck_id": truck_id,
            "eld_provider": "mobile_app",
            "lat": req.lat,
            "lng": req.lng,
            "speed_mph": req.speed_mph,
            "heading": int(req.heading or 0),
            "ts": req.ts
        }).execute()

        # Update driver last_location (jsonb)
        get_supabase().table("drivers").update({
            "last_location": {
                "lat": req.lat,
                "lng": req.lng,
                "accuracy": req.accuracy,
                "speed_mph": req.speed_mph
            },
            "last_location_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", driver_id).execute()

        return {"status": "location recorded"}

    except Exception as e:
        log.error("Location update failed: %s", e)
        # Don't fail — telemetry is best-effort
        return {"status": "recorded"}


# ────────────────────────────────────────────────────────────────────────────
# DOCUMENT UPLOAD
# ────────────────────────────────────────────────────────────────────────────

@router.post("/documents/upload")
async def upload_driver_document(
    doc_type: str,
    session: DriverSession,
    file: UploadFile = File(...),
):
    """Upload driver document (BOL, POD, Lumper receipt).

    Saves to Supabase Storage and metadata to document_vault table.
    Accepted doc_types: bol, pod, lumper, insurance, medical_card
    """
    driver_id = session["driver_id"]

    # Validate document type
    valid_types = {"bol", "pod", "lumper", "insurance", "medical_card"}
    if doc_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"doc_type must be one of: {valid_types}"
        )

    # Validate file
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="filename required"
        )

    # Get driver carrier_id
    try:
        result = get_supabase().table("drivers").select(
            "id, carrier_id"
        ).eq("id", driver_id).single().execute()
        carrier_id = result.data["carrier_id"]
    except Exception as e:
        log.error("Failed to get driver: %s", e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="driver not found"
        )

    # Upload to Supabase Storage
    try:
        file_content = await file.read()
        storage_path = f"{carrier_id}/{driver_id}/{doc_type}/{file.filename}"

        get_supabase().storage.from_("driver-documents").upload(
            path=storage_path,
            file=file_content,
            file_options={"content-type": file.content_type or "application/octet-stream"}
        )

        # Generate signed URL (7-day expiry)
        signed_url = get_supabase().storage.from_("driver-documents").create_signed_url(
            path=storage_path,
            expires_in=604800  # 7 days
        )

        # Store metadata in document_vault
        doc_result = get_supabase().table("document_vault").insert({
            "carrier_id": carrier_id,
            "doc_type": doc_type.upper(),
            "filename": file.filename,
            "storage_path": storage_path,
            "file_size_kb": len(file_content) // 1024,
            "mime_type": file.content_type or "application/octet-stream",
            "scan_status": "pending",
            "uploaded_by": driver_id,
            "bucket": "driver-documents"
        }).execute()

        return DocumentUploadResponse(
            document_id=doc_result.data[0]["id"],
            url=f"/storage/v1/object/public/driver-documents/{storage_path}",
            signed_url=signed_url.get("signedURL", "")
        )

    except Exception as e:
        log.error("Document upload failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="upload failed"
        )


# ────────────────────────────────────────────────────────────────────────────
# DRIVER PROFILE
# ────────────────────────────────────────────────────────────────────────────

@router.get("/profile")
async def get_driver_full_profile(session: DriverSession):
    """Get complete driver profile (loads, earnings, documents)."""
    driver_id = session["driver_id"]

    try:
        # Get driver
        driver_result = get_supabase().table("drivers").select(
            "id, carrier_id, first_name, last_name, phone_e164, cdl_number, stripe_account_id, stripe_account_status"
        ).eq("id", driver_id).single().execute()

        driver = driver_result.data

        # Get current load
        load_result = get_supabase().table("loads").select(
            "id, load_number, status, rate_total, miles"
        ).eq("driver_id", driver_id).neq("status", "delivered").limit(1).execute()

        current_load = load_result.data[0] if load_result.data else None

        # Get this week's earnings
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=now.weekday())

        earnings_result = get_supabase().table("loads").select(
            "rate_total, miles"
        ).eq("driver_id", driver_id).eq("status", "delivered").gte(
            "delivered_at", week_start.isoformat()
        ).execute()

        week_earnings = sum(l.get("rate_total", 0) for l in earnings_result.data or [])

        # Get documents
        docs_result = get_supabase().table("document_vault").select(
            "id, doc_type, filename"
        ).eq("carrier_id", driver["carrier_id"]).order(
            "created_at", desc=True
        ).limit(10).execute()

        return {
            "driver": {
                "id": driver["id"],
                "name": f"{driver['first_name']} {driver['last_name']}".strip(),
                "phone": driver["phone_e164"],
                "cdl": driver["cdl_number"]
            },
            "current_load": current_load,
            "week_earnings": week_earnings,
            "payout_status": driver["stripe_account_status"],
            "recent_documents": docs_result.data or []
        }

    except Exception as e:
        log.error("Failed to get profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="profile fetch failed"
        )


# ────────────────────────────────────────────────────────────────────────────
# AVAILABLE LOADS — load board for drivers
# ────────────────────────────────────────────────────────────────────────────

@router.get("/loads")
async def get_available_loads(session: DriverSession):
    """Return loads for this driver: carrier pool (available/offered/pending) +
    loads dispatched directly to this driver (dispatched/in_transit)."""
    driver_id = session["driver_id"]

    _LOAD_FIELDS = (
        "id, load_number, origin_city, origin_state, dest_city, dest_state, "
        "pickup_address, delivery_address, pickup_at, delivery_at, "
        "rate_total, rate_per_mile, miles, commodity, weight_lbs, "
        "equipment_type, broker_name, broker_phone, special_instructions, "
        "status, driver_code, driver_id, truck_id"
    )
    sb = get_supabase()
    loads: list[dict] = []
    seen_ids: set[str] = set()

    try:
        driver_result = sb.table("drivers").select("carrier_id").eq(
            "id", driver_id
        ).single().execute()
        carrier_id = driver_result.data.get("carrier_id")

        # 1. Carrier pool — loads available to any driver on this carrier
        if carrier_id:
            pool = sb.table("loads").select(_LOAD_FIELDS).eq(
                "carrier_id", carrier_id
            ).in_(
                "status", ["available", "offered", "pending"]
            ).order("pickup_at", desc=False).limit(50).execute()
            for row in (pool.data or []):
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    loads.append(row)

        # 2. Loads dispatched directly to this driver (by driver_code or driver_id)
        for field in ("driver_code", "driver_id"):
            dispatched = sb.table("loads").select(_LOAD_FIELDS).eq(
                field, driver_id
            ).in_(
                "status", ["dispatched", "confirmed", "in_transit"]
            ).order("pickup_at", desc=False).limit(20).execute()
            for row in (dispatched.data or []):
                if row["id"] not in seen_ids:
                    seen_ids.add(row["id"])
                    loads.append(row)

    except Exception as e:
        log.error("Failed to get available loads: %s", e)
        raise HTTPException(status_code=500, detail="failed to fetch loads")

    return {"loads": loads, "count": len(loads)}


@router.post("/loads/{load_id}/accept")
async def accept_load(load_id: str, session: DriverSession):
    """Driver accepts an offered load. Sets driver_id and transitions to confirmed."""
    driver_id = session["driver_id"]

    try:
        load_result = get_supabase().table("loads").select(
            "id, status, carrier_id"
        ).eq("id", load_id).single().execute()

        load = load_result.data
        if not load:
            raise HTTPException(status_code=404, detail="load not found")

        if load.get("status") not in ("available", "offered", "pending"):
            raise HTTPException(
                status_code=409,
                detail=f"Load cannot be accepted in status '{load.get('status')}'"
            )

        get_supabase().table("loads").update({
            "driver_id": driver_id,
            "status":    "confirmed",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", load_id).execute()

        # Notify dispatch via agent log
        get_supabase().table("agent_log").insert({
            "agent":   "falcon",
            "action":  "load_accepted",
            "payload": {"load_id": load_id, "driver_id": driver_id},
            "result":  "confirmed",
        }).execute()

        return {"ok": True, "load_id": load_id, "status": "confirmed"}

    except HTTPException:
        raise
    except Exception as e:
        log.error("Load accept failed: %s", e)
        raise HTTPException(status_code=500, detail="accept failed")


@router.post("/loads/{load_id}/decline")
async def decline_load(load_id: str, session: DriverSession):
    """Driver declines an offered load."""
    driver_id = session["driver_id"]

    try:
        load_result = get_supabase().table("loads").select(
            "id, status"
        ).eq("id", load_id).single().execute()

        load = load_result.data
        if not load:
            raise HTTPException(status_code=404, detail="load not found")

        if load.get("status") not in ("available", "offered", "pending"):
            raise HTTPException(
                status_code=409,
                detail=f"Load cannot be declined in status '{load.get('status')}'"
            )

        # Return to available pool — clear driver assignment if any
        get_supabase().table("loads").update({
            "driver_id": None,
            "status":    "available",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", load_id).execute()

        get_supabase().table("agent_log").insert({
            "agent":   "falcon",
            "action":  "load_declined",
            "payload": {"load_id": load_id, "driver_id": driver_id},
            "result":  "available",
        }).execute()

        return {"ok": True, "load_id": load_id, "status": "available"}

    except HTTPException:
        raise
    except Exception as e:
        log.error("Load decline failed: %s", e)
        raise HTTPException(status_code=500, detail="decline failed")


@router.post("/loads/{load_id}/pickup")
async def confirm_pickup(load_id: str, session: DriverSession):
    """Driver confirms load pickup — transitions status to in_transit."""
    driver_id = session["driver_id"]

    try:
        load_result = get_supabase().table("loads").select(
            "id, driver_id, status"
        ).eq("id", load_id).eq("driver_id", driver_id).single().execute()

        if not load_result.data:
            raise HTTPException(status_code=404, detail="load not found or not assigned to you")

        if load_result.data.get("status") not in ("confirmed", "dispatched"):
            raise HTTPException(status_code=409, detail="load must be confirmed before pickup")

        get_supabase().table("loads").update({
            "status":    "in_transit",
            "pickup_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", load_id).execute()

        return {"ok": True, "load_id": load_id, "status": "in_transit"}

    except HTTPException:
        raise
    except Exception as e:
        log.error("Pickup confirm failed: %s", e)
        raise HTTPException(status_code=500, detail="pickup confirmation failed")


@router.post("/loads/{load_id}/deliver")
async def confirm_delivery(load_id: str, session: DriverSession):
    """Driver confirms delivery — transitions status to delivered."""
    driver_id = session["driver_id"]

    try:
        load_result = get_supabase().table("loads").select(
            "id, driver_id, status"
        ).eq("id", load_id).eq("driver_id", driver_id).single().execute()

        if not load_result.data:
            raise HTTPException(status_code=404, detail="load not found or not assigned to you")

        if load_result.data.get("status") != "in_transit":
            raise HTTPException(status_code=409, detail="load must be in transit to deliver")

        get_supabase().table("loads").update({
            "status":       "delivered",
            "delivered_at": datetime.now(timezone.utc).isoformat(),
            "updated_at":   datetime.now(timezone.utc).isoformat(),
        }).eq("id", load_id).execute()

        return {"ok": True, "load_id": load_id, "status": "delivered"}

    except HTTPException:
        raise
    except Exception as e:
        log.error("Delivery confirm failed: %s", e)
        raise HTTPException(status_code=500, detail="delivery confirmation failed")


# ────────────────────────────────────────────────────────────────────────────
# HOS — Hours of Service (live data from driver_hos_status)
# ────────────────────────────────────────────────────────────────────────────

@router.get("/hos")
async def get_driver_hos(session: DriverSession):
    """Return current HOS status for the authenticated driver."""
    driver_id = session["driver_id"]

    try:
        result = get_supabase().table("driver_hos_status").select(
            "duty_status, hours_driven_today, hours_on_duty_today, "
            "hours_remaining_drive, hours_remaining_shift, cycle_hours_used, "
            "drive_remaining_min, shift_remaining_min, cycle_remaining_min, "
            "violation_flag, violation_flags, last_reset_at, updated_at"
        ).eq("driver_id", driver_id).order("updated_at", desc=True).limit(1).execute()

        if result.data:
            hos = result.data[0]
            return {
                "duty_status":           hos.get("duty_status", "off_duty"),
                "hours_driven_today":    float(hos.get("hours_driven_today") or 0),
                "hours_on_duty_today":   float(hos.get("hours_on_duty_today") or 0),
                "hours_remaining_drive": float(hos.get("hours_remaining_drive") or 11.0),
                "hours_remaining_shift": float(hos.get("hours_remaining_shift") or 14.0),
                "cycle_hours_used":      float(hos.get("cycle_hours_used") or 0),
                "drive_remaining_min":   hos.get("drive_remaining_min", 660),
                "shift_remaining_min":   hos.get("shift_remaining_min", 840),
                "cycle_remaining_min":   hos.get("cycle_remaining_min", 4200),
                "violation_flag":        bool(hos.get("violation_flag", False)),
                "violation_flags":       hos.get("violation_flags") or [],
                "last_reset_at":         hos.get("last_reset_at"),
                "updated_at":            hos.get("updated_at"),
            }

        # No record yet — return clean slate (no violations)
        return {
            "duty_status":           "off_duty",
            "hours_driven_today":    0.0,
            "hours_on_duty_today":   0.0,
            "hours_remaining_drive": 11.0,
            "hours_remaining_shift": 14.0,
            "cycle_hours_used":      0.0,
            "drive_remaining_min":   660,
            "shift_remaining_min":   840,
            "cycle_remaining_min":   4200,
            "violation_flag":        False,
            "violation_flags":       [],
            "last_reset_at":         None,
            "updated_at":            None,
        }
    except Exception as e:
        log.error("HOS fetch failed: %s", e)
        raise HTTPException(status_code=500, detail="HOS fetch failed")


@router.post("/hos/duty-status")
async def update_duty_status(body: dict, session: DriverSession):
    """Driver updates their duty status (driving, on_duty, sleeper, off_duty)."""
    driver_id = session["driver_id"]
    new_status = body.get("duty_status")
    valid_statuses = {"driving", "on_duty", "sleeper", "off_duty"}

    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"duty_status must be one of {valid_statuses}")

    try:
        driver_result = get_supabase().table("drivers").select(
            "carrier_id, driver_code"
        ).eq("id", driver_id).single().execute()
        driver = driver_result.data

        get_supabase().table("driver_hos_status").upsert({
            "driver_id":   driver_id,
            "carrier_id":  driver.get("carrier_id"),
            "driver_code": driver.get("driver_code"),
            "duty_status": new_status,
            "updated_at":  datetime.now(timezone.utc).isoformat(),
        }, on_conflict="driver_id").execute()

        return {"ok": True, "duty_status": new_status}
    except Exception as e:
        log.error("HOS duty status update failed: %s", e)
        raise HTTPException(status_code=500, detail="duty status update failed")


# ────────────────────────────────────────────────────────────────────────────
# VEHICLE INSPECTION (DVIR)
# ────────────────────────────────────────────────────────────────────────────

class DVIRRequest(BaseModel):
    inspection_type: str = "pre_trip"  # pre_trip | post_trip | en_route
    odometer: int | None = None
    defects: list[str] = []
    defects_corrected: bool = True
    safe_to_operate: bool = True
    remarks: str | None = None


@router.post("/inspection")
async def submit_dvir(req: DVIRRequest, session: DriverSession):
    """Submit Driver Vehicle Inspection Report (DVIR)."""
    driver_id = session["driver_id"]

    valid_types = {"pre_trip", "post_trip", "en_route"}
    if req.inspection_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"inspection_type must be one of {valid_types}")

    try:
        driver_result = get_supabase().table("drivers").select(
            "carrier_id, truck_id"
        ).eq("id", driver_id).single().execute()
        driver = driver_result.data

        result = get_supabase().table("driver_dvir").insert({
            "driver_id":         driver_id,
            "carrier_id":        driver.get("carrier_id"),
            "vehicle_id":        driver.get("truck_id"),
            "truck_id":          driver.get("truck_id"),
            "inspection_type":   req.inspection_type,
            "odometer":          req.odometer,
            "defects":           req.defects,
            "defects_corrected": req.defects_corrected,
            "safe_to_operate":   req.safe_to_operate,
            "condition":         "satisfactory" if req.safe_to_operate else "unsatisfactory",
            "remarks":           req.remarks,
            "inspected_at":      datetime.now(timezone.utc).isoformat(),
            "submitted_at":      datetime.now(timezone.utc).isoformat(),
        }).execute()

        return {"ok": True, "inspection_id": result.data[0]["id"] if result.data else None}
    except Exception as e:
        log.error("DVIR submission failed: %s", e)
        raise HTTPException(status_code=500, detail="inspection submission failed")


@router.get("/inspections")
async def get_driver_inspections(session: DriverSession, limit: int = 10):
    """Get recent DVIR inspections for the authenticated driver."""
    driver_id = session["driver_id"]

    try:
        result = get_supabase().table("driver_dvir").select(
            "id, inspection_type, odometer, defects, safe_to_operate, inspected_at"
        ).eq("driver_id", driver_id).order("inspected_at", desc=True).limit(limit).execute()

        return {"inspections": result.data or []}
    except Exception as e:
        log.error("Inspection fetch failed: %s", e)
        raise HTTPException(status_code=500, detail="inspection fetch failed")


# ────────────────────────────────────────────────────────────────────────────
# DETENTION PAY
# ────────────────────────────────────────────────────────────────────────────

class DetentionRequest(BaseModel):
    load_id: str
    location: str  # "pickup" or "delivery"
    detention_start: str  # ISO datetime
    detention_end: str | None = None  # ISO datetime — None if still waiting
    reason: str | None = None


@router.post("/detention")
async def report_detention(req: DetentionRequest, session: DriverSession):
    """Driver reports detention time at a pickup or delivery location."""
    driver_id = session["driver_id"]

    valid_locations = {"pickup", "delivery"}
    if req.location not in valid_locations:
        raise HTTPException(status_code=400, detail="location must be 'pickup' or 'delivery'")

    try:
        # Verify load belongs to this driver
        load_result = get_supabase().table("loads").select(
            "id, driver_id, load_number, broker_name, broker_phone"
        ).eq("id", req.load_id).eq("driver_id", driver_id).single().execute()

        if not load_result.data:
            raise HTTPException(status_code=404, detail="load not found or not assigned to you")

        load = load_result.data

        # Calculate duration if end time provided
        duration_min: int | None = None
        if req.detention_end:
            try:
                start_dt = datetime.fromisoformat(req.detention_start.replace("Z", "+00:00"))
                end_dt   = datetime.fromisoformat(req.detention_end.replace("Z", "+00:00"))
                duration_min = int((end_dt - start_dt).total_seconds() / 60)
            except ValueError:
                pass

        # Standard detention rate: $50/hour after 2-hour free time
        detention_pay: float | None = None
        if duration_min is not None and duration_min > 120:
            billable_min = duration_min - 120
            detention_pay = round((billable_min / 60) * 50, 2)

        result = get_supabase().table("fuel_advance_requests").insert({
            "driver_id":       driver_id,
            "load_id":         req.load_id,
            "request_type":    "detention",
            "location":        req.location,
            "detention_start": req.detention_start,
            "detention_end":   req.detention_end,
            "duration_min":    duration_min,
            "detention_pay":   detention_pay,
            "amount":          detention_pay or 0,
            "reason":          req.reason,
            "status":          "pending",
            "created_at":      datetime.now(timezone.utc).isoformat(),
        }).execute()

        return {
            "ok":            True,
            "load_number":   load.get("load_number"),
            "duration_min":  duration_min,
            "detention_pay": detention_pay,
            "status":        "pending",
            "note":          "Detention claim submitted. Dispatch will follow up with broker."
                             if detention_pay else "Detention logged. Free-time clock running.",
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("Detention report failed: %s", e)
        raise HTTPException(status_code=500, detail="detention report failed")


@router.get("/detention")
async def get_detention_history(session: DriverSession):
    """Get driver's detention claims."""
    driver_id = session["driver_id"]

    try:
        result = get_supabase().table("fuel_advance_requests").select(
            "id, load_id, location, detention_start, detention_end, duration_min, detention_pay, status, created_at"
        ).eq("driver_id", driver_id).eq("request_type", "detention").order(
            "created_at", desc=True
        ).limit(20).execute()

        return {"detentions": result.data or []}
    except Exception as e:
        log.error("Detention history failed: %s", e)
        raise HTTPException(status_code=500, detail="detention history failed")



# ────────────────────────────────────────────────────────────────────────────
# FUEL ADVANCE REQUESTS
# ────────────────────────────────────────────────────────────────────────────

class FuelAdvanceRequest(BaseModel):
    driver_name: str | None = None
    amount: float
    location: str
    notes: str | None = None
    load_id: str | None = None


@router.post("/fuel-advance")
async def submit_fuel_advance(req: FuelAdvanceRequest, session: DriverSession):
    """Driver submits a fuel advance request."""
    driver_id = session["driver_id"]
    try:
        result = get_supabase().table("driver_fuel_requests").insert({
            "driver_id":   driver_id,
            "driver_name": req.driver_name,
            "amount":      req.amount,
            "location":    req.location,
            "notes":       req.notes,
            "load_id":     req.load_id,
            "status":      "pending",
            "created_at":  datetime.now(timezone.utc).isoformat(),
        }).execute()
        return {"ok": True, "id": (result.data or [{}])[0].get("id")}
    except Exception as e:
        log.error("Fuel advance submission failed: %s", e)
        raise HTTPException(status_code=500, detail="fuel advance submission failed")


@router.get("/fuel-advance")
async def get_fuel_advance_history(session: DriverSession):
    """Get driver's fuel advance request history."""
    driver_id = session["driver_id"]
    try:
        result = get_supabase().table("driver_fuel_requests").select(
            "id, amount, location, notes, status, load_id, created_at, approved_at"
        ).eq("driver_id", driver_id).order("created_at", desc=True).limit(20).execute()
        return {"requests": result.data or []}
    except Exception as e:
        log.error("Fuel advance history failed: %s", e)
        raise HTTPException(status_code=500, detail="fuel advance history failed")


# ────────────────────────────────────────────────────────────────────────────
# LIGHT FLEET — driver-auth-protected earnings & compliance (for LF PWA)
# ────────────────────────────────────────────────────────────────────────────

@router.get("/lf/earnings")
async def lf_driver_earnings(session: DriverSession, period: str = "week"):
    """Return Light Fleet driver earnings — accessible via driver session token."""
    driver_id = session["driver_id"]

    try:
        from ..agents import earnings_aggregator
        return {
            "driver_id": driver_id,
            "period": period,
            "summary": earnings_aggregator.get_earnings(driver_id, period),
            "breakdown": earnings_aggregator.get_platform_breakdown(driver_id, period),
            "trend": earnings_aggregator.get_weekly_trend(driver_id),
        }
    except Exception as e:
        log.error("LF earnings fetch failed: %s", e)
        raise HTTPException(status_code=500, detail="earnings fetch failed")


@router.get("/lf/compliance")
async def lf_driver_compliance(session: DriverSession):
    """Return Light Fleet driver compliance status — accessible via driver session token."""
    driver_id = session["driver_id"]

    try:
        from ..agents import compliance_autopilot
        return compliance_autopilot.get_compliance_status(driver_id)
    except Exception as e:
        log.error("LF compliance fetch failed: %s", e)
        raise HTTPException(status_code=500, detail="compliance fetch failed")


@router.post("/lf/certifications/{cert_type}")
async def lf_upload_certification(
    cert_type: str,
    session: DriverSession,
    file: UploadFile = File(...),
    issued_date: str | None = None,
    expiry_date: str | None = None,
):
    """Upload a certification document (CPR, HIPAA, or specimen handling).

    cert_type: cpr | hipaa | specimen
    issued_date, expiry_date: YYYY-MM-DD strings
    """
    valid_types = {"cpr", "hipaa", "specimen"}
    if cert_type not in valid_types:
        raise HTTPException(status_code=422, detail=f"cert_type must be one of {valid_types}")

    driver_id = session["driver_id"]
    sb = get_supabase()

    if not file.filename:
        raise HTTPException(status_code=422, detail="file required")

    file_bytes = await file.read()
    ext = (file.filename or "cert.pdf").rsplit(".", 1)[-1].lower() or "pdf"
    storage_path = f"certs/{driver_id}/{cert_type}.{ext}"

    # Upload to driver-documents bucket
    try:
        try:
            sb.storage.from_("driver-documents").remove([storage_path])
        except Exception:
            pass
        sb.storage.from_("driver-documents").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": file.content_type or "application/octet-stream"},
        )
        signed = sb.storage.from_("driver-documents").create_signed_url(storage_path, expires_in=604800)
        cert_url = signed.get("signedURL") or signed.get("signed_url", "")
    except Exception as e:
        log.error("Cert upload failed driver=%s cert=%s: %s", driver_id, cert_type, e)
        raise HTTPException(status_code=500, detail="cert upload failed")

    # Map to DB columns
    col_map = {
        "cpr":      ("cpr_certified_at",      "cpr_expires_at",      "cpr_cert_url"),
        "hipaa":    ("hipaa_trained_at",       "hipaa_expires_at",    "hipaa_cert_url"),
        "specimen": ("specimen_certified_at",  "specimen_expires_at", "specimen_cert_url"),
    }
    issued_col, expiry_col, url_col = col_map[cert_type]
    update: dict = {url_col: cert_url}
    if issued_date:
        update[issued_col] = issued_date
    if expiry_date:
        update[expiry_col] = expiry_date
    elif cert_type in ("cpr", "specimen") and issued_date:
        # Default: 1-year expiry
        from datetime import date, timedelta
        try:
            exp = date.fromisoformat(issued_date) + timedelta(days=365)
            update[expiry_col] = exp.isoformat()
        except Exception:
            pass
    elif cert_type == "hipaa" and issued_date:
        # HIPAA training valid for 2 years
        from datetime import date, timedelta
        try:
            exp = date.fromisoformat(issued_date) + timedelta(days=730)
            update[expiry_col] = exp.isoformat()
        except Exception:
            pass

    sb.table("light_vehicle_drivers").update(update).eq("id", driver_id).execute()

    return {
        "ok":       True,
        "cert_type":cert_type,
        "cert_url": cert_url,
        **{k: v for k, v in update.items() if k != url_col},
    }


@router.get("/lf/certifications")
async def lf_get_certifications(session: DriverSession):
    """Return current certification status for the LF driver."""
    driver_id = session["driver_id"]
    row = get_supabase().table("light_vehicle_drivers").select(
        "cpr_certified_at,cpr_expires_at,cpr_cert_url,"
        "hipaa_trained_at,hipaa_expires_at,hipaa_cert_url,"
        "specimen_certified_at,specimen_expires_at,specimen_cert_url"
    ).eq("id", driver_id).maybe_single().execute().data or {}
    return {"driver_id": driver_id, "certifications": row}


@router.post("/lf/payout/setup")
async def lf_payout_setup(session: DriverSession):
    """Initialize Stripe Connect Express onboarding for an LF driver."""
    driver_id = session["driver_id"]
    sb = get_supabase()

    driver_row = sb.table("light_vehicle_drivers").select(
        "id, name, email, phone_e164, stripe_account_id, stripe_account_status"
    ).eq("id", driver_id).maybe_single().execute().data or {}

    if driver_row.get("stripe_account_status") == "connected":
        raise HTTPException(status_code=400, detail="payout already set up")

    from ..settings import get_settings
    import stripe as _stripe
    s = get_settings()
    if not s.stripe_secret_key:
        raise HTTPException(status_code=503, detail="stripe not configured")
    _stripe.api_key = s.stripe_secret_key

    try:
        account_id = driver_row.get("stripe_account_id")
        if not account_id:
            name_parts = (driver_row.get("name") or "").split(" ", 1)
            acct = _stripe.Account.create(
                type="express",
                country="US",
                email=driver_row.get("email") or "",
                settings={"payouts": {"schedule": {"interval": "manual"}}},
                metadata={"driver_id": driver_id, "driver_type": "light_fleet"},
            )
            account_id = acct.id
            sb.table("light_vehicle_drivers").update({
                "stripe_account_id": account_id,
                "stripe_account_status": "onboarding",
            }).eq("id", driver_id).execute()

        link = _stripe.AccountLink.create(
            account=account_id,
            refresh_url="https://www.3lakeslogistics.com/driver-pwa/lf.html?payout=refresh",
            return_url="https://www.3lakeslogistics.com/driver-pwa/lf.html?payout=success",
            type="account_onboarding",
        )
        sb.table("light_vehicle_drivers").update({
            "stripe_onboarding_url": link.url,
        }).eq("id", driver_id).execute()
        return {"onboarding_url": link.url, "account_id": account_id}
    except _stripe.error.StripeError as e:
        log.error("Stripe Connect setup failed for LF driver %s: %s", driver_id, e)
        raise HTTPException(status_code=502, detail=f"stripe error: {e.user_message or str(e)}")


@router.get("/lf/payout/status")
async def lf_payout_status(session: DriverSession):
    """Return current Stripe Connect status and pending earnings for LF driver."""
    driver_id = session["driver_id"]
    sb = get_supabase()

    driver_row = sb.table("light_vehicle_drivers").select(
        "stripe_account_id, stripe_account_status, stripe_payouts_enabled"
    ).eq("id", driver_id).maybe_single().execute().data or {}

    # Sum unsettled earnings from ledger
    try:
        rows = sb.table("atomic_ledger").select("financial_payload").eq(
            "event_type", "lf_trip_settled"
        ).contains("logistics_payload", {"carrier_id": driver_id}).execute().data or []
        pending_balance = sum(
            float((r.get("financial_payload") or {}).get("driver_net", 0))
            for r in rows
        )
    except Exception:
        pending_balance = 0.0

    # Subtract already-processed payouts
    try:
        paid_rows = sb.table("lf_driver_payouts").select("net_cents").eq(
            "driver_id", driver_id
        ).in_("status", ["processing", "paid"]).execute().data or []
        paid_total = sum(r["net_cents"] / 100 for r in paid_rows)
        pending_balance = max(0.0, pending_balance - paid_total)
    except Exception:
        pass

    # Instant pay eligibility: 6 months on the platform
    instant_pay_eligible = False
    try:
        joined_row = sb.table("light_vehicle_drivers").select("created_at").eq(
            "id", driver_id
        ).maybe_single().execute().data or {}
        joined_at_str = joined_row.get("created_at") or ""
        if joined_at_str:
            joined_at = datetime.fromisoformat(joined_at_str.replace("Z", "+00:00"))
            instant_pay_eligible = (datetime.now(timezone.utc) - joined_at).days >= 180
    except Exception:
        pass

    return {
        "stripe_status":          driver_row.get("stripe_account_status", "not_started"),
        "payouts_enabled":        driver_row.get("stripe_payouts_enabled", False),
        "stripe_account_id":      driver_row.get("stripe_account_id"),
        "pending_balance_usd":    round(pending_balance, 2),
        "instant_pay_eligible":   instant_pay_eligible,
        "instant_pay_unlock_note": "Instant pay unlocks after 6 months on the platform"
                                   if not instant_pay_eligible else None,
    }


# Instant-pay processing fee: 0.75%
_INSTANT_PAY_FEE = 0.0075


@router.post("/lf/instant-pay")
async def lf_instant_pay(body: dict, session: DriverSession):
    """Request instant same-day payout for LF driver.

    Deducts a 0.75% processing fee, creates a Stripe Transfer to the driver's
    connected account, then triggers an instant Stripe Payout to their debit card.
    """
    driver_id = session["driver_id"]
    amount = float(body.get("amount", 0))
    if amount <= 0:
        raise HTTPException(status_code=422, detail="amount must be positive")

    sb = get_supabase()
    driver_row = sb.table("light_vehicle_drivers").select(
        "stripe_account_id, stripe_account_status, stripe_payouts_enabled"
    ).eq("id", driver_id).maybe_single().execute().data or {}

    if driver_row.get("stripe_account_status") != "connected":
        raise HTTPException(status_code=400, detail="payout not set up — complete Stripe onboarding first")

    # Instant pay requires 6 months of tenure
    try:
        joined_row = sb.table("light_vehicle_drivers").select("created_at").eq(
            "id", driver_id
        ).maybe_single().execute().data or {}
        joined_at_str = joined_row.get("created_at") or ""
        if joined_at_str:
            joined_at = datetime.fromisoformat(joined_at_str.replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - joined_at).days < 180:
                raise HTTPException(
                    status_code=403,
                    detail="Instant pay is a privilege earned after 6 months on the platform",
                )
    except HTTPException:
        raise
    except Exception:
        pass  # if we can't determine tenure, allow through

    stripe_account_id = driver_row["stripe_account_id"]
    fee  = round(amount * _INSTANT_PAY_FEE, 2)
    net  = round(amount - fee, 2)
    gross_cents   = int(amount * 100)
    fee_cents     = int(fee * 100)
    net_cents     = int(net * 100)

    if net_cents <= 0:
        raise HTTPException(status_code=422, detail="amount too small after processing fee")

    from ..settings import get_settings
    import stripe as _stripe
    s = get_settings()
    if not s.stripe_secret_key:
        raise HTTPException(status_code=503, detail="stripe not configured")
    _stripe.api_key = s.stripe_secret_key

    now = datetime.now(timezone.utc)
    payout_record_id = None
    try:
        # 1. Create payout record (pending)
        rec = sb.table("lf_driver_payouts").insert({
            "driver_id":          driver_id,
            "payout_type":        "instant",
            "gross_cents":        gross_cents,
            "platform_fee_cents": 0,           # already deducted at settlement
            "instant_fee_cents":  fee_cents,
            "net_cents":          net_cents,
            "status":             "processing",
            "requested_at":       now.isoformat(),
        }).execute()
        payout_record_id = (rec.data or [{}])[0].get("id")

        # 2. Transfer from platform balance → driver connected account
        transfer = _stripe.Transfer.create(
            amount=net_cents,
            currency="usd",
            destination=stripe_account_id,
            metadata={"driver_id": driver_id, "payout_type": "instant",
                      "record_id": str(payout_record_id or "")},
        )
        transfer_id = transfer.id

        # 3. Trigger instant payout on connected account (to debit card)
        payout_id = None
        try:
            payout = _stripe.Payout.create(
                amount=net_cents,
                currency="usd",
                method="instant",
                stripe_account=stripe_account_id,
                metadata={"driver_id": driver_id, "transfer_id": transfer_id},
            )
            payout_id = payout.id
        except _stripe.error.StripeError as pe:
            # Instant payout may not be available on this account — fall back to standard
            log.warning("Instant payout unavailable for driver %s (%s); transfer sent, standard payout will follow", driver_id, pe)

        # 4. Update payout record with Stripe IDs
        update: dict = {
            "stripe_transfer_id": transfer_id,
            "status":             "paid" if payout_id else "processing",
            "processed_at":       now.isoformat(),
        }
        if payout_id:
            update["stripe_payout_id"] = payout_id
            update["paid_at"] = now.isoformat()
        if payout_record_id:
            sb.table("lf_driver_payouts").update(update).eq("id", payout_record_id).execute()

        return {
            "ok":               True,
            "driver_id":        driver_id,
            "gross":            amount,
            "instant_fee":      fee,
            "net":              net,
            "fee_pct":          "0.75%",
            "transfer_id":      transfer_id,
            "payout_id":        payout_id,
            "status":           "paid" if payout_id else "processing",
        }

    except _stripe.error.StripeError as e:
        log.error("Stripe instant pay failed for LF driver %s: %s", driver_id, e)
        if payout_record_id:
            sb.table("lf_driver_payouts").update({
                "status": "failed", "failure_reason": str(e.user_message or e)[:300]
            }).eq("id", payout_record_id).execute()
        raise HTTPException(status_code=502, detail=f"payment failed: {e.user_message or str(e)}")
    except Exception as e:
        log.error("LF instant pay unexpected error for driver %s: %s", driver_id, e)
        raise HTTPException(status_code=500, detail="instant pay failed")


@router.post("/lf/trips/{trip_id}/pod")
async def lf_submit_pod(
    trip_id: str,
    session: DriverSession,
    photo: UploadFile = File(None),
    signature: UploadFile = File(None),
    recipient_name: str | None = None,
    notes: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
):
    """Driver submits Proof of Delivery — photo + optional e-signature.

    Accepts multipart/form-data with:
      photo         — delivery photo (jpeg/png/webp, required)
      signature     — customer e-signature PNG (optional)
      recipient_name — name of person who signed/received
      notes         — any delivery notes
      lat, lng      — GPS coordinates at capture time
    """
    driver_id = session["driver_id"]
    sb = get_supabase()

    # Verify this trip belongs to this driver
    trip_res = sb.table("light_vehicle_trips").select(
        "id, driver_id, trip_type, status"
    ).eq("id", trip_id).maybe_single().execute()
    trip = trip_res.data or {}
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")
    if str(trip.get("driver_id")) != driver_id:
        raise HTTPException(status_code=403, detail="not your trip")
    if trip.get("status") not in ("in_progress", "arrived", "completed"):
        raise HTTPException(status_code=409, detail=f"cannot submit POD in status '{trip.get('status')}'")

    if not photo:
        raise HTTPException(status_code=422, detail="photo is required for POD")

    now = datetime.now(timezone.utc)
    photo_path     = None
    signature_path = None
    photo_url      = None
    signature_url  = None

    # ── Upload photo ─────────────────────────────────────────────────────────
    try:
        photo_bytes = await photo.read()
        ext = (photo.filename or "photo.jpg").rsplit(".", 1)[-1].lower() or "jpg"
        photo_path = f"{trip_id}/photo.{ext}"
        sb.storage.from_("lf-pod").upload(
            path=photo_path,
            file=photo_bytes,
            file_options={"content-type": photo.content_type or "image/jpeg"},
        )
        # Generate 7-day signed URL
        signed = sb.storage.from_("lf-pod").create_signed_url(photo_path, expires_in=604800)
        photo_url = signed.get("signedURL") or signed.get("signed_url", "")
    except Exception as e:
        log.error("POD photo upload failed trip=%s: %s", trip_id, e)
        raise HTTPException(status_code=500, detail="photo upload failed")

    # ── Upload signature (optional) ───────────────────────────────────────────
    if signature:
        try:
            sig_bytes = await signature.read()
            signature_path = f"{trip_id}/signature.png"
            sb.storage.from_("lf-pod").upload(
                path=signature_path,
                file=sig_bytes,
                file_options={"content-type": "image/png"},
            )
            signed = sb.storage.from_("lf-pod").create_signed_url(signature_path, expires_in=604800)
            signature_url = signed.get("signedURL") or signed.get("signed_url", "")
        except Exception as e:
            log.warning("POD signature upload failed trip=%s: %s", trip_id, e)

    # ── Write POD record ──────────────────────────────────────────────────────
    try:
        sb.table("lf_pod_records").upsert({
            "trip_id":        trip_id,
            "driver_id":      driver_id,
            "photo_path":     photo_path,
            "signature_path": signature_path,
            "photo_url":      photo_url,
            "signature_url":  signature_url,
            "captured_lat":   lat,
            "captured_lng":   lng,
            "recipient_name": recipient_name,
            "notes":          notes,
            "created_at":     now.isoformat(),
        }, on_conflict="trip_id").execute()
    except Exception as e:
        log.error("POD record write failed trip=%s: %s", trip_id, e)

    # ── Update trip pod_url + mark completed if still in progress ────────────
    try:
        trip_update: dict = {"pod_url": photo_url}
        if trip.get("status") in ("in_progress", "arrived"):
            trip_update.update({"status": "completed", "completed_at": now.isoformat()})
        sb.table("light_vehicle_trips").update(trip_update).eq("id", trip_id).execute()
    except Exception as e:
        log.warning("Trip POD update failed trip=%s: %s", trip_id, e)

    return {
        "ok":             True,
        "trip_id":        trip_id,
        "photo_url":      photo_url,
        "signature_url":  signature_url,
        "pod_complete":   True,
        "captured_at":    now.isoformat(),
    }


@router.get("/lf/trips/{trip_id}/pod")
async def lf_get_pod(trip_id: str, session: DriverSession):
    """Return the POD record for a completed trip."""
    driver_id = session["driver_id"]
    sb = get_supabase()
    rec = sb.table("lf_pod_records").select("*").eq("trip_id", trip_id).maybe_single().execute().data
    if not rec:
        raise HTTPException(status_code=404, detail="no POD found for this trip")
    if str(rec.get("driver_id")) != driver_id:
        raise HTTPException(status_code=403, detail="not your trip")
    # Refresh signed URLs if they've been stored as permanent paths
    for field, path_field in [("photo_url", "photo_path"), ("signature_url", "signature_path")]:
        if rec.get(path_field) and not rec.get(field):
            try:
                signed = sb.storage.from_("lf-pod").create_signed_url(rec[path_field], expires_in=604800)
                rec[field] = signed.get("signedURL") or signed.get("signed_url", "")
            except Exception:
                pass
    return rec


@router.get("/lf/trips")
async def lf_driver_trips(session: DriverSession, status: str | None = None, limit: int = 30):
    """Return Light Fleet trips assigned to the authenticated driver."""
    driver_id = session["driver_id"]

    try:
        q = get_supabase().table("light_vehicle_trips").select(
            "id, trip_type, status, pickup_address, dropoff_address, "
            "scheduled_at, started_at, completed_at, rate_total, rate_per_mile, "
            "estimated_miles, passenger_name, notes, created_at"
        ).eq("driver_id", driver_id).order("scheduled_at", desc=True).limit(limit)

        if status:
            q = q.eq("status", status)

        result = q.execute()
        return {"trips": result.data or [], "count": len(result.data or [])}
    except Exception as e:
        log.error("LF trips fetch failed: %s", e)
        raise HTTPException(status_code=500, detail="trips fetch failed")

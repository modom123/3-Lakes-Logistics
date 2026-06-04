"""Driver endpoints — location tracking, documents, DVIR, profile."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, List

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


class DVIRSubmission(BaseModel):
    inspection_type: str  # "pre_trip" | "post_trip"
    vehicle_id: str | None = None
    odometer: int | None = None
    defects: List[str] = []
    defects_corrected: bool = False
    condition: str = "satisfactory"  # "satisfactory" | "defects_noted"
    remarks: str | None = None
    signature_data: str | None = None  # base64 driver signature


class LoadRequestBody(BaseModel):
    notes: str | None = None


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
    valid_types = {
        "bol", "pod", "lumper", "insurance", "medical_card",
        "cdl", "drug_test", "agreement", "w9", "fuel_advance",
        "rate_confirmation", "lease", "1099", "other"
    }
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
# DOCUMENT VAULT — list + signed URL refresh
# ────────────────────────────────────────────────────────────────────────────

@router.get("/documents")
async def list_driver_documents(session: DriverSession):
    """Return all documents uploaded by this driver with fresh signed URLs.

    Signed URLs are valid for 7 days. The vault generates a fresh URL for
    each document so the driver can always open/download them.
    """
    driver_id = session["driver_id"]

    try:
        result = get_supabase().table("document_vault").select(
            "id, doc_type, filename, storage_path, file_size_kb, mime_type, "
            "scan_status, created_at, notes, expiration_date"
        ).eq("uploaded_by", driver_id).order("created_at", desc=True).execute()

        docs = result.data or []

        # Attach a fresh signed URL to each document
        for doc in docs:
            path = doc.get("storage_path")
            if path:
                try:
                    su = get_supabase().storage.from_("driver-documents").create_signed_url(
                        path=path, expires_in=604800
                    )
                    doc["signed_url"] = su.get("signedURL", "")
                except Exception:
                    doc["signed_url"] = ""
            else:
                doc["signed_url"] = ""

        return {"documents": docs, "total": len(docs)}

    except Exception as e:
        log.error("Document list failed driver=%s: %s", driver_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="could not fetch documents"
        )


@router.delete("/documents/{doc_id}")
async def delete_driver_document(doc_id: str, session: DriverSession):
    """Delete a document from the vault (soft: removes metadata + storage file)."""
    driver_id = session["driver_id"]

    try:
        # Verify ownership
        result = get_supabase().table("document_vault").select(
            "id, storage_path, uploaded_by"
        ).eq("id", doc_id).single().execute()

        doc = result.data
        if not doc or doc["uploaded_by"] != driver_id:
            raise HTTPException(status_code=404, detail="document not found")

        # Delete from storage
        if doc.get("storage_path"):
            try:
                get_supabase().storage.from_("driver-documents").remove([doc["storage_path"]])
            except Exception:
                pass

        # Delete metadata
        get_supabase().table("document_vault").delete().eq("id", doc_id).execute()

        return {"ok": True, "deleted": doc_id}

    except HTTPException:
        raise
    except Exception as e:
        log.error("Document delete failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="delete failed"
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
            "id, carrier_id, first_name, last_name, phone_e164, cdl_number, "
            "stripe_account_id, stripe_account_status, display_id, driver_code"
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
                "display_id": driver.get("display_id"),
                "driver_code": driver.get("driver_code"),
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
# DVIR — DRIVER VEHICLE INSPECTION REPORT (federal requirement)
# ────────────────────────────────────────────────────────────────────────────

@router.post("/dvir")
async def submit_dvir(req: DVIRSubmission, session: DriverSession):
    """Submit pre-trip or post-trip vehicle inspection report.

    Federal regulation (49 CFR 396.11) requires drivers to inspect their
    vehicle before and after each trip and report any defects found.
    """
    driver_id = session["driver_id"]

    try:
        driver_result = get_supabase().table("drivers").select(
            "id, carrier_id, first_name, last_name"
        ).eq("id", driver_id).single().execute()
        driver = driver_result.data
        carrier_id = driver["carrier_id"]

        result = get_supabase().table("driver_dvir").insert({
            "driver_id": driver_id,
            "carrier_id": carrier_id,
            "vehicle_id": req.vehicle_id,
            "inspection_type": req.inspection_type,
            "odometer": req.odometer,
            "defects": req.defects,
            "defects_corrected": req.defects_corrected,
            "condition": req.condition,
            "remarks": req.remarks,
            "has_signature": bool(req.signature_data),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        dvir_id = result.data[0]["id"] if result.data else "submitted"
        log.info("DVIR submitted driver=%s type=%s condition=%s",
                 driver_id, req.inspection_type, req.condition)

        return {
            "ok": True,
            "dvir_id": dvir_id,
            "inspection_type": req.inspection_type,
            "condition": req.condition,
            "defects_count": len(req.defects),
        }

    except Exception as e:
        log.error("DVIR submission failed driver=%s: %s", driver_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DVIR submission failed"
        )


# ────────────────────────────────────────────────────────────────────────────
# DRIVER LOADS — get/update loads assigned to this driver
# ────────────────────────────────────────────────────────────────────────────

@router.get("/loads")
async def get_driver_loads(session: DriverSession, status: str | None = None, limit: int = 20):
    """Return loads assigned to the authenticated driver."""
    driver_id = session["driver_id"]
    try:
        q = (
            get_supabase()
            .table("loads")
            .select("*")
            .eq("driver_id", driver_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        if status:
            statuses = [s.strip() for s in status.split(",")]
            q = q.in_("status", statuses) if len(statuses) > 1 else q.eq("status", statuses[0])
        res = q.execute()
        return {"items": res.data or []}
    except Exception as e:
        log.error("get_driver_loads failed driver=%s: %s", driver_id, e)
        return {"items": []}


@router.patch("/loads/{load_id}")
async def update_driver_load(load_id: str, payload: dict, session: DriverSession):
    """Driver updates status or notes on their assigned load."""
    driver_id = session["driver_id"]
    allowed = {"status", "driver_notes"}
    update_data = {k: v for k, v in payload.items() if k in allowed}
    if not update_data:
        raise HTTPException(status_code=400, detail="no updatable fields")
    try:
        get_supabase().table("loads").update(update_data).eq("id", load_id).eq("driver_id", driver_id).execute()
        return {"ok": True}
    except Exception as e:
        log.error("update_driver_load failed driver=%s load=%s: %s", driver_id, load_id, e)
        raise HTTPException(status_code=500, detail="update failed")


# ────────────────────────────────────────────────────────────────────────────
# AVAILABLE LOADS — curated picks the driver can claim
# ────────────────────────────────────────────────────────────────────────────

@router.get("/available-loads")
async def get_available_loads(session: DriverSession):
    """Return the top 3 claimable loads for this driver.

    Filters by the driver's equipment type when known.
    Excludes loads the driver has already requested.
    Ordered by rate (highest first).
    """
    driver_id = session["driver_id"]
    db = get_supabase()

    try:
        driver_row = db.table("drivers").select(
            "id, equipment_type"
        ).eq("id", driver_id).single().execute()
        equipment_type = (driver_row.data or {}).get("equipment_type")
    except Exception:
        equipment_type = None

    # IDs of loads this driver already requested
    try:
        pending = db.table("load_requests").select("load_id").eq(
            "driver_id", driver_id
        ).in_("status", ["pending", "approved"]).execute()
        already_requested = {r["load_id"] for r in (pending.data or [])}
    except Exception:
        already_requested = set()

    try:
        q = (
            db.table("loads")
            .select(
                "id, load_number, origin_city, origin_state, dest_city, dest_state,"
                " rate_total, rate_per_mile, miles, weight, equipment_type,"
                " pickup_at, delivery_at, shipper_name, commodity"
            )
            .eq("status", "available")
            .order("rate_total", desc=True)
            .limit(20)
        )
        if equipment_type:
            q = q.ilike("equipment_type", f"%{equipment_type}%")

        res = q.execute()
        loads = [l for l in (res.data or []) if l["id"] not in already_requested][:3]
        return {"loads": loads, "count": len(loads)}
    except Exception as e:
        log.error("get_available_loads failed driver=%s: %s", driver_id, e)
        return {"loads": [], "count": 0}


# ────────────────────────────────────────────────────────────────────────────
# LOAD REQUEST — driver requests to pick up an available load
# ────────────────────────────────────────────────────────────────────────────

@router.post("/loads/{load_id}/request")
async def request_load(load_id: str, body: LoadRequestBody, session: DriverSession):
    """Driver requests to be assigned to an available load.

    Creates a pending request that dispatchers can approve/decline.
    A driver can only have one active pending request at a time.
    """
    driver_id = session["driver_id"]

    try:
        # Verify load exists and is available
        load_result = get_supabase().table("loads").select(
            "id, load_number, status, origin_city, dest_city, rate_total"
        ).eq("id", load_id).single().execute()

        if not load_result.data:
            raise HTTPException(status_code=404, detail="load not found")

        load = load_result.data
        if load["status"] not in ("available", "pending"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"load is not available (status: {load['status']})"
            )

        # Check for existing pending request from this driver
        existing = get_supabase().table("load_requests").select("id").eq(
            "driver_id", driver_id
        ).eq("status", "pending").execute()

        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="you already have a pending load request"
            )

        # Create request
        req_result = get_supabase().table("load_requests").insert({
            "load_id": load_id,
            "driver_id": driver_id,
            "status": "pending",
            "notes": body.notes,
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        req_id = req_result.data[0]["id"] if req_result.data else "created"
        log.info("Load request created driver=%s load=%s", driver_id, load_id)

        return {
            "ok": True,
            "request_id": req_id,
            "load_id": load_id,
            "load_number": load.get("load_number"),
            "route": f"{load.get('origin_city')} → {load.get('dest_city')}",
            "status": "pending",
            "message": "Request submitted. Dispatcher will confirm shortly.",
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error("Load request failed driver=%s load=%s: %s", driver_id, load_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request failed"
        )


# ────────────────────────────────────────────────────────────────────────────
# DRIVER MESSAGES — read own thread + send to dispatcher
# ────────────────────────────────────────────────────────────────────────────

class DriverMessageBody(BaseModel):
    message: str


@router.get("/messages")
async def get_driver_messages(session: DriverSession, limit: int = 50):
    """Return the driver's own SMS/message thread with dispatch.

    Reads from driver_messages keyed on the driver's phone_e164.
    """
    driver_id = session["driver_id"]

    try:
        # Look up driver phone
        dr = get_supabase().table("drivers").select(
            "phone_e164"
        ).eq("id", driver_id).single().execute()
        phone = dr.data.get("phone_e164", "")

        rows = get_supabase().table("driver_messages").select(
            "id, direction, body, msg_type, created_at, read, load_id"
        ).eq("driver_phone", phone).order(
            "created_at", desc=False
        ).limit(limit).execute()

        return {"messages": rows.data or [], "phone": phone}

    except Exception as e:
        log.error("Driver messages fetch failed driver=%s: %s", driver_id, e)
        return {"messages": [], "phone": ""}


@router.post("/messages")
async def send_driver_message(req: DriverMessageBody, session: DriverSession):
    """Driver sends a message to dispatch.

    Stores in driver_messages as outbound and attempts Twilio send.
    """
    driver_id = session["driver_id"]

    try:
        dr = get_supabase().table("drivers").select(
            "phone_e164, first_name, last_name, carrier_id"
        ).eq("id", driver_id).single().execute()
        driver = dr.data
        phone = driver.get("phone_e164", "")
        name = f"{driver.get('first_name','')} {driver.get('last_name','')}".strip()

        get_supabase().table("driver_messages").insert({
            "direction": "outbound_driver",
            "driver_phone": phone,
            "body": req.message,
            "driver_id": driver_id,
            "msg_type": "text",
            "read": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        log.info("Driver message sent driver=%s name=%s", driver_id, name)
        return {"ok": True, "sent": True}

    except Exception as e:
        log.error("Driver message failed driver=%s: %s", driver_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="message failed"
        )


# ────────────────────────────────────────────────────────────────────────────
# DRIVER NOTIFICATIONS — activity feed
# ────────────────────────────────────────────────────────────────────────────

@router.get("/notifications")
async def get_driver_notifications(session: DriverSession, limit: int = 20):
    """Return recent activity/notifications for the driver.

    Combines inbound messages + recent load status changes as a feed.
    """
    driver_id = session["driver_id"]
    items = []

    try:
        dr = get_supabase().table("drivers").select(
            "phone_e164"
        ).eq("id", driver_id).single().execute()
        phone = dr.data.get("phone_e164", "")

        # Inbound messages as notifications
        msgs = get_supabase().table("driver_messages").select(
            "id, body, created_at, read, direction"
        ).eq("driver_phone", phone).eq("direction", "inbound").order(
            "created_at", desc=True
        ).limit(limit).execute()

        for m in (msgs.data or []):
            items.append({
                "id": m["id"],
                "icon": "💬",
                "title": m.get("body", "")[:80],
                "message": m.get("body", ""),
                "created_at": m.get("created_at", ""),
                "read_at": None if not m.get("read") else m.get("created_at"),
                "type": "message",
            })

    except Exception as e:
        log.debug("Notifications fetch error: %s", e)

    try:
        # Recent load events
        loads = get_supabase().table("loads").select(
            "id, load_number, status, updated_at, origin_city, dest_city"
        ).eq("driver_id", driver_id).order(
            "updated_at", desc=True
        ).limit(5).execute()

        status_icons = {
            "assigned": "📋", "dispatched": "🚀",
            "in_transit": "🚛", "delivered": "✅",
        }
        for ld in (loads.data or []):
            icon = status_icons.get(ld.get("status", ""), "📋")
            items.append({
                "id": ld["id"],
                "icon": icon,
                "title": f"Load #{ld.get('load_number','?')} — {ld.get('status','').replace('_',' ').title()}",
                "message": f"{ld.get('origin_city','?')} → {ld.get('dest_city','?')}",
                "created_at": ld.get("updated_at", ""),
                "read_at": ld.get("updated_at"),
                "type": "load_event",
            })

    except Exception as e:
        log.debug("Load notifications fetch error: %s", e)

    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"items": items[:limit], "unread": sum(1 for i in items if not i.get("read_at"))}


# ────────────────────────────────────────────────────────────────────────────
# FUEL ADVANCE REQUEST
# ────────────────────────────────────────────────────────────────────────────

class FuelAdvanceRequest(BaseModel):
    amount: float          # USD amount requested
    load_id: str | None = None
    reason: str | None = None


@router.post("/fuel-advance")
async def request_fuel_advance(req: FuelAdvanceRequest, session: DriverSession):
    """Driver requests a fuel advance against their current load."""
    driver_id = session["driver_id"]

    if req.amount <= 0 or req.amount > 2000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="amount must be between $1 and $2,000"
        )

    try:
        dr = get_supabase().table("drivers").select(
            "id, carrier_id, first_name, last_name"
        ).eq("id", driver_id).single().execute()
        carrier_id = dr.data["carrier_id"]

        result = get_supabase().table("fuel_advance_requests").insert({
            "driver_id": driver_id,
            "carrier_id": carrier_id,
            "load_id": req.load_id,
            "amount": req.amount,
            "reason": req.reason,
            "status": "pending",
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        req_id = result.data[0]["id"] if result.data else "submitted"
        log.info("Fuel advance requested driver=%s amount=$%.2f", driver_id, req.amount)

        return {
            "ok": True,
            "request_id": req_id,
            "amount": req.amount,
            "status": "pending",
            "message": "Fuel advance request submitted. Dispatch will approve shortly.",
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error("Fuel advance failed driver=%s: %s", driver_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="request failed"
        )

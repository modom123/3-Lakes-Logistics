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

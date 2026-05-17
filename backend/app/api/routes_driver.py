"""Driver endpoints — location tracking, documents, profile."""
from __future__ import annotations

from datetime import datetime, timezone
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
            "heading_deg": req.heading or 0,
            "fuel_level_pct": None,
            "engine_hours": None,
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
    file: UploadFile = File(...),
    session: DriverSession
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
            "scan_status": "pending"
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
            "id, first_name, last_name, phone_e164, cdl_number, stripe_account_id, stripe_account_status"
        ).eq("id", driver_id).single().execute()

        driver = driver_result.data

        # Get current load
        load_result = get_supabase().table("loads").select(
            "id, load_number, status, rate_total, miles"
        ).eq("driver_id", driver_id).neq("status", "delivered").single().execute()

        current_load = load_result.data if load_result.data else None

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

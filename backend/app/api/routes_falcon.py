"""FALCON API — carrier portal for TruckSmarter / external O-O clients.

Authentication: HMAC-signed token delivered in dispatch SMS link.
Token format (base64url):  load_id:driver_code:hmac_sig
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from pydantic import BaseModel

from ..supabase_client import get_supabase
from ..logging_service import get_logger
from ..settings import get_settings

log = get_logger("3ll.falcon")
router = APIRouter(prefix="/api/falcon", tags=["falcon"])

_FALCON_BASE_URL = "https://three-lakes-logistics-api.onrender.com/falcon"


# ── Token helpers ─────────────────────────────────────────────────────────────

def _secret() -> bytes:
    s = get_settings()
    return (s.supabase_service_role_key or "falcon-secret-3ll-iebc").encode()


def generate_falcon_token(load_id: str, driver_code: str) -> str:
    """Generate a signed FALCON dispatch token."""
    payload = f"{load_id}:{driver_code}".encode()
    sig = hmac.new(_secret(), payload, hashlib.sha256).hexdigest()[:20]
    raw = f"{load_id}:{driver_code}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_token(token: str) -> tuple[str, str]:
    """Decode and validate token → (load_id, driver_code). Raises 401 on failure."""
    try:
        padded = token + "=" * (4 - len(token) % 4)
        raw = base64.urlsafe_b64decode(padded).decode()
        parts = raw.split(":")
        if len(parts) < 3:
            raise ValueError("bad format")
        load_id, driver_code, sig = parts[0], parts[1], parts[2]
        payload = f"{load_id}:{driver_code}".encode()
        expected = hmac.new(_secret(), payload, hashlib.sha256).hexdigest()[:20]
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        return load_id, driver_code
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired FALCON token: {exc}")


def falcon_portal_url(load_id: str, driver_code: str) -> str:
    token = generate_falcon_token(load_id, driver_code)
    return f"{_FALCON_BASE_URL}?t={token}"


# ── Auth ──────────────────────────────────────────────────────────────────────

_LOAD_FIELDS = (
    "id, load_number, status, origin_city, origin_state, dest_city, dest_state, "
    "pickup_address, delivery_address, pickup_at, delivery_at, "
    "rate_total, rate_per_mile, miles, equipment_type, broker_name, broker_phone, "
    "commodity, weight_lbs, special_instructions, driver_code, truck_id, "
    "pickup_confirmed_at, delivered_at, updated_at"
)


@router.get("/auth")
def falcon_auth(t: str = Query(..., description="FALCON dispatch token")):
    """Validate token and return load + session. Called on FALCON app load."""
    load_id, driver_code = _decode_token(t)
    sb = get_supabase()
    try:
        result = sb.table("loads").select(_LOAD_FIELDS).eq("id", load_id).single().execute()
        load = result.data
        if not load:
            raise HTTPException(status_code=404, detail="Load not found")
        stored_code = load.get("driver_code")
        if stored_code and stored_code != driver_code:
            raise HTTPException(status_code=403, detail="Token does not match this load")
        return {"authenticated": True, "load_id": load_id, "driver_code": driver_code, "load": load, "token": t}
    except HTTPException:
        raise
    except Exception as exc:
        log.error("FALCON auth error: %s", exc)
        raise HTTPException(status_code=500, detail="Auth failed")


# ── Load data ─────────────────────────────────────────────────────────────────

@router.get("/load/{load_id}")
def get_load(load_id: str, t: str = Query(...)):
    """Fetch current load data for FALCON carrier view."""
    tok_load_id, _ = _decode_token(t)
    if tok_load_id != load_id:
        raise HTTPException(status_code=403, detail="Token mismatch")
    sb = get_supabase()
    result = sb.table("loads").select(_LOAD_FIELDS).eq("id", load_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Load not found")
    return result.data


# ── Status updates ────────────────────────────────────────────────────────────

_STATUS_ORDER = ["dispatched", "confirmed", "en_route", "at_pickup", "in_transit", "at_delivery", "delivered"]

_TIMESTAMP_FIELDS = {
    "in_transit":   "pickup_confirmed_at",
    "delivered":    "delivered_at",
}

class StatusBody(BaseModel):
    status: str
    notes: str | None = None
    lat: float | None = None
    lng: float | None = None


@router.post("/load/{load_id}/status")
def update_status(load_id: str, body: StatusBody, t: str = Query(...)):
    """Carrier taps a status milestone on FALCON — updates loads table."""
    tok_load_id, driver_code = _decode_token(t)
    if tok_load_id != load_id:
        raise HTTPException(status_code=403, detail="Token mismatch")
    if body.status not in _STATUS_ORDER:
        raise HTTPException(status_code=422, detail=f"Unknown status. Valid: {_STATUS_ORDER}")
    sb = get_supabase()
    try:
        load = sb.table("loads").select("status").eq("id", load_id).single().execute().data or {}
        current_idx = _STATUS_ORDER.index(load.get("status", "dispatched")) if load.get("status") in _STATUS_ORDER else 0
        new_idx = _STATUS_ORDER.index(body.status)
        if new_idx < current_idx:
            raise HTTPException(status_code=409, detail=f"Cannot move backwards from '{load.get('status')}' to '{body.status}'")
        now = datetime.now(timezone.utc).isoformat()
        update: dict = {"status": body.status, "updated_at": now}
        ts_field = _TIMESTAMP_FIELDS.get(body.status)
        if ts_field:
            update[ts_field] = now
        sb.table("loads").update(update).eq("id", load_id).execute()
        try:
            sb.table("agent_log").insert({
                "agent": "falcon",
                "action": f"status_{body.status}",
                "payload": {"load_id": load_id, "driver_code": driver_code,
                            "status": body.status, "lat": body.lat, "lng": body.lng},
                "result": "ok",
            }).execute()
        except Exception:
            pass
        return {"ok": True, "load_id": load_id, "status": body.status, "updated_at": now}
    except HTTPException:
        raise
    except Exception as exc:
        log.error("FALCON status update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Status update failed")


# ── Document uploads ──────────────────────────────────────────────────────────

@router.post("/load/{load_id}/bol")
async def upload_bol(load_id: str, t: str = Query(...), file: UploadFile = File(...)):
    """Carrier uploads Bill of Lading at pickup."""
    tok_load_id, driver_code = _decode_token(t)
    if tok_load_id != load_id:
        raise HTTPException(status_code=403, detail="Token mismatch")
    sb = get_supabase()
    file_bytes = await file.read()
    ext = (file.filename or "bol.pdf").rsplit(".", 1)[-1].lower() or "pdf"
    path = f"falcon/{load_id}/bol.{ext}"
    try:
        try:
            sb.storage.from_("driver-documents").remove([path])
        except Exception:
            pass
        sb.storage.from_("driver-documents").upload(
            path=path, file=file_bytes,
            file_options={"content-type": file.content_type or "application/pdf"},
        )
        signed = sb.storage.from_("driver-documents").create_signed_url(path, expires_in=604800)
        url = signed.get("signedURL") or signed.get("signed_url", "")
        sb.table("loads").update({"bol_url": url, "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", load_id).execute()
        try:
            sb.table("agent_log").insert({
                "agent": "falcon", "action": "bol_uploaded",
                "payload": {"load_id": load_id, "driver_code": driver_code, "url": url},
                "result": "ok",
            }).execute()
        except Exception:
            pass
        return {"ok": True, "doc_type": "bol", "url": url}
    except Exception as exc:
        log.error("FALCON BOL upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="BOL upload failed")


@router.post("/load/{load_id}/pod")
async def upload_pod(load_id: str, t: str = Query(...), file: UploadFile = File(...)):
    """Carrier uploads Proof of Delivery at destination."""
    tok_load_id, driver_code = _decode_token(t)
    if tok_load_id != load_id:
        raise HTTPException(status_code=403, detail="Token mismatch")
    sb = get_supabase()
    file_bytes = await file.read()
    ext = (file.filename or "pod.jpg").rsplit(".", 1)[-1].lower() or "jpg"
    path = f"falcon/{load_id}/pod.{ext}"
    try:
        try:
            sb.storage.from_("driver-documents").remove([path])
        except Exception:
            pass
        sb.storage.from_("driver-documents").upload(
            path=path, file=file_bytes,
            file_options={"content-type": file.content_type or "image/jpeg"},
        )
        signed = sb.storage.from_("driver-documents").create_signed_url(path, expires_in=604800)
        url = signed.get("signedURL") or signed.get("signed_url", "")
        sb.table("loads").update({"pod_url": url, "status": "delivered",
                                  "delivered_at": datetime.now(timezone.utc).isoformat(),
                                  "updated_at": datetime.now(timezone.utc).isoformat()}).eq("id", load_id).execute()
        try:
            sb.table("agent_log").insert({
                "agent": "falcon", "action": "pod_uploaded",
                "payload": {"load_id": load_id, "driver_code": driver_code, "url": url},
                "result": "ok",
            }).execute()
        except Exception:
            pass
        return {"ok": True, "doc_type": "pod", "url": url}
    except Exception as exc:
        log.error("FALCON POD upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="POD upload failed")


# ── Payment status ────────────────────────────────────────────────────────────

@router.get("/load/{load_id}/pay")
def get_pay_status(load_id: str, t: str = Query(...)):
    """Return payment status and net earnings breakdown for FALCON carrier."""
    tok_load_id, _ = _decode_token(t)
    if tok_load_id != load_id:
        raise HTTPException(status_code=403, detail="Token mismatch")
    sb = get_supabase()
    try:
        load = sb.table("loads").select("rate_total, status, delivered_at, broker_name").eq("id", load_id).single().execute().data or {}
        gross = float(load.get("rate_total") or 0)
        fee = round(gross * 0.15, 2)
        net = round(gross - fee, 2)
        status = load.get("status", "dispatched")
        if status == "delivered":
            pay_status = "invoice_submitted"
            eta = "3–5 business days · same-day available with factoring"
        elif status in ("at_delivery", "in_transit"):
            pay_status = "in_transit"
            eta = "Invoice auto-submits on delivery"
        else:
            pay_status = "pending"
            eta = "Calculated after delivery"
        return {
            "load_id": load_id,
            "gross_rate": gross,
            "platform_fee_pct": 15,
            "platform_fee": fee,
            "your_net": net,
            "pay_status": pay_status,
            "eta": eta,
            "factoring_available": status == "delivered",
            "broker": load.get("broker_name"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Messages ──────────────────────────────────────────────────────────────────

class MessageBody(BaseModel):
    message: str
    priority: str = "normal"


@router.post("/load/{load_id}/message")
def send_message(load_id: str, body: MessageBody, t: str = Query(...)):
    """Carrier sends message to IEBC dispatch from FALCON."""
    _, driver_code = _decode_token(t)
    if not body.message.strip():
        raise HTTPException(status_code=422, detail="message required")
    sb = get_supabase()
    try:
        sb.table("agent_log").insert({
            "agent": "falcon",
            "action": "carrier_message",
            "payload": {"load_id": load_id, "driver_code": driver_code,
                        "message": body.message, "priority": body.priority},
            "result": "received",
        }).execute()
    except Exception:
        pass
    return {"ok": True, "note": "Message sent to IEBC dispatch"}


# ── Document Vault ────────────────────────────────────────────────────────────

_VAULT_DOC_TYPES = {"rate_con", "lumper", "scale_ticket", "detention", "fuel_receipt", "other"}


@router.get("/load/{load_id}/docs")
def list_vault_docs(load_id: str, t: str = Query(...)):
    """Return all vault documents uploaded for this load (excludes BOL/POD)."""
    tok_load_id, _ = _decode_token(t)
    if tok_load_id != load_id:
        raise HTTPException(status_code=403, detail="Token mismatch")
    sb = get_supabase()
    try:
        result = sb.table("load_documents").select(
            "id, doc_type, url, file_name, uploaded_at"
        ).eq("load_id", load_id).execute()
        return {"docs": result.data or []}
    except Exception:
        # Table may not exist yet — return empty list gracefully
        return {"docs": []}


@router.post("/load/{load_id}/docs")
async def upload_vault_doc(
    load_id: str,
    t: str = Query(...),
    doc_type: str = Query(..., description="rate_con | lumper | scale_ticket | detention | fuel_receipt | other"),
    file: UploadFile = File(...),
):
    """Carrier uploads a vault document (non-BOL/POD) via FALCON."""
    tok_load_id, driver_code = _decode_token(t)
    if tok_load_id != load_id:
        raise HTTPException(status_code=403, detail="Token mismatch")
    if doc_type not in _VAULT_DOC_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown doc_type. Valid: {sorted(_VAULT_DOC_TYPES)}")
    sb = get_supabase()
    file_bytes = await file.read()
    ext = (file.filename or f"{doc_type}.pdf").rsplit(".", 1)[-1].lower() or "pdf"
    path = f"falcon/{load_id}/{doc_type}.{ext}"
    try:
        try:
            sb.storage.from_("driver-documents").remove([path])
        except Exception:
            pass
        sb.storage.from_("driver-documents").upload(
            path=path, file=file_bytes,
            file_options={"content-type": file.content_type or "application/pdf"},
        )
        signed = sb.storage.from_("driver-documents").create_signed_url(path, expires_in=604800)
        url = signed.get("signedURL") or signed.get("signed_url", "")
        now = datetime.now(timezone.utc).isoformat()
        # Upsert into load_documents table (graceful if table doesn't exist)
        try:
            sb.table("load_documents").upsert({
                "load_id": load_id,
                "doc_type": doc_type,
                "url": url,
                "file_name": file.filename or f"{doc_type}.{ext}",
                "uploaded_by": driver_code,
                "uploaded_at": now,
            }, on_conflict="load_id,doc_type").execute()
        except Exception:
            pass
        try:
            sb.table("agent_log").insert({
                "agent": "falcon", "action": "vault_doc_uploaded",
                "payload": {"load_id": load_id, "driver_code": driver_code,
                            "doc_type": doc_type, "url": url},
                "result": "ok",
            }).execute()
        except Exception:
            pass
        return {"ok": True, "doc_type": doc_type, "url": url}
    except Exception as exc:
        log.error("FALCON vault upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="Vault upload failed")


# ── FALCON Board (Eagle Eye internal) ─────────────────────────────────────────

@router.get("/board")
def falcon_board(status: str | None = None, limit: int = 100):
    """Eagle Eye internal — live board of all FALCON-dispatched loads."""
    sb = get_supabase()
    try:
        q = sb.table("loads").select(
            "id, load_number, status, origin_city, origin_state, dest_city, dest_state, "
            "rate_total, miles, equipment_type, broker_name, driver_code, truck_id, "
            "pickup_at, delivery_at, pickup_confirmed_at, delivered_at, updated_at, "
            "bol_url, pod_url"
        ).not_.is_("driver_code", "null").order("updated_at", desc=True).limit(limit)
        if status:
            q = q.eq("status", status)
        result = q.execute()
        loads = result.data or []
        for row in loads:
            if row.get("id") and row.get("driver_code"):
                row["falcon_token"] = generate_falcon_token(str(row["id"]), str(row["driver_code"]))
        return {"loads": loads, "count": len(loads)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

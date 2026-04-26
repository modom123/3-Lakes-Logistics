"""Document vault — upload BOL/POD/rate-conf/insurance PDFs to Supabase Storage
and register metadata in the document_vault table.

Routes:
  POST /api/docs/upload          — multipart file upload
  GET  /api/docs/                — list vault entries (filter by carrier/doc_type)
  GET  /api/docs/{doc_id}        — single doc metadata + signed URL
  POST /api/docs/{doc_id}/scan   — re-trigger CLM / Scout OCR scan
  DELETE /api/docs/{doc_id}      — soft-delete (sets deleted_at)
"""
from __future__ import annotations

import mimetypes
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])

_BUCKET = "documents"
_ALLOWED_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/tiff",
}
_MAX_BYTES = 20 * 1024 * 1024  # 20 MB


def _storage_path(carrier_id: str, doc_type: str, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    uid = uuid.uuid4().hex[:8]
    return f"{carrier_id}/{doc_type}/{uid}_{filename}"[:200]


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    carrier_id: str = Form(...),
    doc_type: str = Form(...),
    load_id: str | None = Form(default=None),
    driver_id: str | None = Form(default=None),
    notes: str | None = Form(default=None),
) -> dict:
    """Upload a document to Supabase Storage and register it in document_vault."""
    valid_types = {"rate_confirmation", "bol", "pod", "insurance", "broker_agreement",
                   "w9", "cdl_scan", "medical_card", "lumper_receipt", "other"}
    if doc_type not in valid_types:
        raise HTTPException(400, f"doc_type must be one of {sorted(valid_types)}")

    content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(415, f"unsupported file type: {content_type}")

    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(413, "file exceeds 20 MB limit")

    sb = get_supabase()
    path = _storage_path(carrier_id, doc_type, file.filename or "upload")

    # Upload to Supabase Storage
    try:
        sb.storage.from_(_BUCKET).upload(
            path=path,
            file=data,
            file_options={"content-type": content_type, "upsert": "false"},
        )
    except Exception as exc:
        raise HTTPException(500, f"storage upload failed: {exc}") from exc

    # Generate a signed URL (valid 7 days)
    try:
        signed = sb.storage.from_(_BUCKET).create_signed_url(path, expires_in=604800)
        signed_url = signed.get("signedURL") or signed.get("signedUrl") or ""
    except Exception:  # noqa: BLE001
        signed_url = ""

    # Register in document_vault
    row = {
        "carrier_id": carrier_id,
        "doc_type": doc_type,
        "storage_path": path,
        "original_filename": file.filename,
        "content_type": content_type,
        "size_bytes": len(data),
        "scan_status": "pending",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    if load_id:
        row["load_id"] = load_id
    if driver_id:
        row["driver_id"] = driver_id
    if notes:
        row["notes"] = notes

    res = sb.table("document_vault").insert(row).execute()
    doc_id = (res.data or [{}])[0].get("id")

    log_agent("scout", "doc_uploaded", carrier_id=carrier_id,
              payload={"doc_type": doc_type, "path": path, "size_bytes": len(data)})

    return {
        "ok": True,
        "doc_id": doc_id,
        "path": path,
        "signed_url": signed_url,
        "size_bytes": len(data),
        "scan_status": "pending",
    }


@router.get("/")
def list_docs(
    carrier_id: str | None = None,
    doc_type: str | None = None,
    scan_status: str | None = None,
    limit: int = 100,
) -> dict:
    q = (
        get_supabase()
        .table("document_vault")
        .select("id,carrier_id,doc_type,original_filename,size_bytes,scan_status,uploaded_at,load_id,driver_id")
        .order("uploaded_at", desc=True)
        .limit(limit)
    )
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if doc_type:
        q = q.eq("doc_type", doc_type)
    if scan_status:
        q = q.eq("scan_status", scan_status)
    res = q.execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.get("/{doc_id}")
def get_doc(doc_id: str) -> dict:
    sb = get_supabase()
    res = sb.table("document_vault").select("*").eq("id", doc_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "document not found")
    doc = res.data

    # Refresh signed URL
    try:
        signed = sb.storage.from_(_BUCKET).create_signed_url(doc["storage_path"], expires_in=3600)
        doc["signed_url"] = signed.get("signedURL") or signed.get("signedUrl") or ""
    except Exception:  # noqa: BLE001
        doc["signed_url"] = ""

    return doc


@router.post("/{doc_id}/scan")
def trigger_scan(doc_id: str) -> dict:
    """Re-trigger OCR scan via Scout agent."""
    sb = get_supabase()
    res = sb.table("document_vault").select("*").eq("id", doc_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "document not found")
    doc = res.data

    # Generate signed URL for Scout
    try:
        signed = sb.storage.from_(_BUCKET).create_signed_url(doc["storage_path"], expires_in=300)
        url = signed.get("signedURL") or signed.get("signedUrl") or ""
    except Exception as exc:
        raise HTTPException(500, f"could not generate signed URL: {exc}") from exc

    from ..agents import scout
    result = scout.run({"file_ref": url, "doc_type": doc.get("doc_type")})

    sb.table("document_vault").update({
        "scan_status": "complete" if result.get("status") == "ok" else "failed",
        "scan_result": result.get("extracted"),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", doc_id).execute()

    return {"ok": True, "doc_id": doc_id, "scan": result}


@router.delete("/{doc_id}")
def delete_doc(doc_id: str) -> dict:
    get_supabase().table("document_vault").update({
        "deleted_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", doc_id).execute()
    return {"ok": True, "doc_id": doc_id}

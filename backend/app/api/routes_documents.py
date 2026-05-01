"""Document upload and retrieval — POST /api/documents/upload, GET /api/documents."""
from __future__ import annotations

import uuid
import mimetypes
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .deps import require_bearer
from ..supabase_client import get_supabase
from ..logging_service import log_agent

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/heic",
    "image/webp",
}

MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


@router.post("/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    carrier_id: str | None = Form(None),
    load_id: str | None = Form(None),
    _: str = Depends(require_bearer),
):
    """Accept a file upload, store in Supabase Storage, index in document_vault."""
    content = await file.read()

    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(413, "File too large — 20 MB max")

    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or ""
    if mime not in ALLOWED_TYPES:
        raise HTTPException(415, f"Unsupported file type: {mime}. Use PDF, JPG, or PNG.")

    doc_id = str(uuid.uuid4())
    ext = (file.filename or "file").rsplit(".", 1)[-1].lower()
    safe_name = f"{doc_id}.{ext}"

    # Storage path: documents/{carrier_id_or_general}/{doc_type}/{filename}
    folder = carrier_id or "general"
    storage_path = f"documents/{folder}/{doc_type}/{safe_name}"

    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")

    # Upload to Supabase Storage bucket "documents"
    try:
        sb.storage.from_("documents").upload(
            path=storage_path,
            file=content,
            file_options={"content-type": mime},
        )
        public_url = sb.storage.from_("documents").get_public_url(storage_path)
    except Exception as exc:
        # If storage bucket not yet created, fall back to storing path only
        public_url = storage_path
        log_agent("scout", "upload_storage_warn", payload={"error": str(exc)})

    # Insert record to document_vault
    row = {
        "id": doc_id,
        "doc_type": doc_type,
        "filename": file.filename or safe_name,
        "storage_path": public_url,
        "file_size_kb": round(len(content) / 1024, 1),
        "scan_status": "pending",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    if carrier_id:
        row["carrier_id"] = carrier_id
    if load_id:
        row["contract_id"] = load_id

    result = sb.table("document_vault").insert(row).execute()
    log_agent("scout", "document_uploaded", payload={"doc_type": doc_type, "filename": file.filename})

    return result.data[0] if result.data else row


@router.get("")
def list_documents(
    carrier_id: str | None = None,
    doc_type: str | None = None,
    scan_status: str | None = None,
    _: str = Depends(require_bearer),
):
    """List documents from document_vault with optional filters."""
    sb = get_supabase()
    if not sb:
        raise HTTPException(503, "Database not configured")
    q = sb.table("document_vault").select("*")
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if doc_type:
        q = q.eq("doc_type", doc_type)
    if scan_status:
        q = q.eq("scan_status", scan_status)
    return q.order("uploaded_at", desc=True).limit(500).execute().data

"""Supabase Storage helpers (step 78 — e-sign PDFs)."""
from __future__ import annotations

import base64
import hashlib
import re

from .logging_service import get_logger

_log = get_logger("3ll.storage")
AGREEMENTS_BUCKET = "agreements"


def _clean_b64(raw: str) -> bytes:
    raw = re.sub(r"^data:application/pdf;base64,", "", raw)
    return base64.b64decode(raw + "==")


def store_agreement_pdf(carrier_id: str, b64_data: str) -> str | None:
    """Upload PDF to Supabase Storage. Returns signed URL or None."""
    try:
        pdf_bytes = _clean_b64(b64_data)
    except Exception:  # noqa: BLE001
        return None
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    path = f"{carrier_id}/{digest[:16]}.pdf"
    try:
        from .supabase_client import get_supabase
        sb = get_supabase()
        try:
            sb.storage.create_bucket(AGREEMENTS_BUCKET, options={"public": False})
        except Exception:  # noqa: BLE001
            pass  # already exists
        sb.storage.from_(AGREEMENTS_BUCKET).upload(
            path, pdf_bytes,
            {"content-type": "application/pdf", "upsert": "true"},
        )
        signed = sb.storage.from_(AGREEMENTS_BUCKET).create_signed_url(path, 60 * 60 * 24 * 365)
        return signed.get("signedURL") or signed.get("signed_url")
    except Exception as exc:  # noqa: BLE001
        _log.warning("storage upload failed: %s", exc)
        return None

"""Document extraction pipeline for the Vault.

Two-path strategy:
  - Digital PDFs  → PyPDF2 text → scan_contract()
  - Scanned/image → Claude Vision API (base64) → scan_contract() output

Call extract_vault_doc(doc_id) to run the full pipeline on any vault document.
Results are stored back in document_vault.extracted_data.
"""
from __future__ import annotations

import base64
import io
import json
import logging
from typing import Any

import anthropic

from ..settings import get_settings
from ..supabase_client import get_supabase
from .scanner import _PROMPTS, _REQUIRED_FIELDS, _SYSTEM

log = logging.getLogger("3ll.clm.doc_extractor")

# Vault doc_type → scanner contract_type mapping
_DOC_TYPE_MAP: dict[str, str] = {
    "rate_con":         "rate_confirmation",
    "rate_confirmation":"rate_confirmation",
    "bol":              "bol",
    "pod":              "pod",
    "broker_agreement": "broker_agreement",
    "agreement":        "broker_agreement",
}

_IMAGE_MIME_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp",
}
_PDF_MIME_TYPE = "application/pdf"


def _signed_url(storage_path: str, bucket: str = "documents") -> str | None:
    try:
        result = get_supabase().storage.from_(bucket).create_signed_url(storage_path, 300)
        return result.get("signedURL") or result.get("signed_url")
    except Exception:
        try:
            result = get_supabase().storage.from_("driver-documents").create_signed_url(storage_path, 300)
            return result.get("signedURL") or result.get("signed_url")
        except Exception:
            return None


def _download_file(storage_path: str, bucket: str) -> bytes | None:
    try:
        data = get_supabase().storage.from_(bucket).download(storage_path)
        return data if isinstance(data, bytes) else bytes(data)
    except Exception:
        try:
            data = get_supabase().storage.from_("driver-documents").download(storage_path)
            return data if isinstance(data, bytes) else bytes(data)
        except Exception:
            return None


def _extract_text_from_pdf(content: bytes) -> str:
    """Extract plain text from a digital (text-layer) PDF via PyPDF2."""
    try:
        import PyPDF2  # noqa: PLC0415
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")
        return "\n".join(pages).strip()
    except Exception as e:
        log.warning("PyPDF2 extraction failed: %s", e)
        return ""


def _scan_with_claude_vision(
    content: bytes,
    mime_type: str,
    contract_type: str,
) -> tuple[dict[str, Any], float, list[str]]:
    """Send file to Claude Vision/Document API and return (extracted, confidence, warnings)."""
    s = get_settings()
    client = anthropic.Anthropic(api_key=s.anthropic_api_key)

    b64 = base64.standard_b64encode(content).decode()

    # Claude supports PDF documents natively via the document block type
    if mime_type == _PDF_MIME_TYPE:
        source_block: dict = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
        }
    else:
        # Normalize mime type for image block
        img_type = mime_type if mime_type in _IMAGE_MIME_TYPES else "image/jpeg"
        source_block = {
            "type": "image",
            "source": {"type": "base64", "media_type": img_type, "data": b64},
        }

    prompt_template = _PROMPTS.get(contract_type, _PROMPTS["rate_confirmation"])
    text_prompt = prompt_template.format(document_text="[See attached document above]")

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    source_block,
                    {"type": "text", "text": text_prompt},
                ],
            }],
        )
        try:
            from ..cost_tracking import track_anthropic as _ta
            _ta("claude-sonnet-4-6", message.usage.input_tokens, message.usage.output_tokens, agent="clm_doc_extractor")
        except Exception:
            pass
        content_text = message.content[0].text.strip()

        if content_text.startswith("```"):
            lines = content_text.split("\n")
            content_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        extracted: dict[str, Any] = json.loads(content_text)
    except json.JSONDecodeError as exc:
        log.warning("Vision scanner JSON parse failed: %s", exc)
        extracted = {}
    except Exception as exc:
        log.error("Vision scanner Claude API error: %s", exc)
        extracted = {}

    required = _REQUIRED_FIELDS.get(contract_type, [])
    warnings = [f"Missing required field: {f}" for f in required if not extracted.get(f)]

    non_null = sum(1 for v in extracted.values() if v is not None and v != {} and v != [])
    confidence = round(non_null / max(len(extracted), 1), 3)

    return extracted, confidence, warnings


def extract_vault_doc(doc_id: str) -> dict:
    """Run the full extraction pipeline on a vault document.

    Downloads from Supabase Storage, chooses the right extraction path,
    calls Claude, and persists results to document_vault.extracted_data.

    Returns a summary dict with keys: doc_id, method, confidence, warnings, extracted.
    """
    from datetime import datetime, timezone  # noqa: PLC0415

    sb = get_supabase()
    res = sb.table("document_vault").select(
        "id,filename,storage_path,bucket,doc_type,mime_type"
    ).eq("id", doc_id).limit(1).execute()

    if not res.data:
        return {"error": "Document not found", "doc_id": doc_id}

    doc = res.data[0]
    storage_path = doc.get("storage_path") or ""
    bucket = doc.get("bucket") or "documents"
    mime_type = (doc.get("mime_type") or "").lower()
    doc_type = doc.get("doc_type") or "rate_con"
    contract_type = _DOC_TYPE_MAP.get(doc_type, "rate_confirmation")

    log.info("extract_vault_doc id=%s type=%s mime=%s", doc_id, doc_type, mime_type)

    # ── Download file ────────────────────────────────────────────────────────
    content = _download_file(storage_path, bucket)
    if not content:
        return {"error": "Could not download file from storage", "doc_id": doc_id}

    # ── Choose extraction path ───────────────────────────────────────────────
    method = "claude_vision"
    extracted: dict[str, Any] = {}
    confidence = 0.0
    warnings: list[str] = []

    if mime_type == _PDF_MIME_TYPE:
        text = _extract_text_from_pdf(content)
        if len(text) > 100:
            # Digital PDF with text layer — use text scanner
            from .scanner import scan_contract  # noqa: PLC0415
            extracted, confidence, warnings = scan_contract(text, contract_type)
            method = "pdf_text"
        else:
            # Scanned/image PDF — fall back to Claude Vision
            extracted, confidence, warnings = _scan_with_claude_vision(content, mime_type, contract_type)
            method = "claude_vision"
    elif mime_type in _IMAGE_MIME_TYPES:
        extracted, confidence, warnings = _scan_with_claude_vision(content, mime_type, contract_type)
        method = "claude_vision"
    else:
        # Unknown type — attempt text extraction first
        text = content.decode("utf-8", errors="ignore")
        if len(text.strip()) > 100:
            from .scanner import scan_contract  # noqa: PLC0415
            extracted, confidence, warnings = scan_contract(text, contract_type)
            method = "pdf_text"
        else:
            return {"error": f"Unsupported file type: {mime_type}", "doc_id": doc_id}

    # ── Persist to document_vault ────────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    sb.table("document_vault").update({
        "extracted_data":    extracted,
        "extract_confidence": confidence,
        "extract_warnings":   warnings or [],
        "extracted_at":       now,
        "extract_method":     method,
    }).eq("id", doc_id).execute()

    log.info(
        "extract_vault_doc complete id=%s method=%s confidence=%.3f warnings=%d",
        doc_id, method, confidence, len(warnings),
    )

    return {
        "ok":         True,
        "doc_id":     doc_id,
        "method":     method,
        "confidence": confidence,
        "warnings":   warnings,
        "extracted":  extracted,
    }

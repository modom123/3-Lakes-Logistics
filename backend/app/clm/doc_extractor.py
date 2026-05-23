"""Document extraction pipeline for the Vault.

Extraction paths:
  1. Digital PDFs      → PyPDF2 text layer → scan_contract()
  2. Scanned/image PDF → Claude Vision (base64 document block)
  3. JPEG / PNG / GIF / WEBP → Claude Vision (base64 image block)
  4. HEIC / HEIF (iPhone photos) → pillow-heif → JPEG → Claude Vision
  5. Large phone photos → Pillow resize + EXIF orientation fix → Claude Vision

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
from .scanner import (
    _PROMPTS, _REQUIRED_FIELDS, _SYSTEM,
    _CLASSIFY_SYSTEM, _CLASSIFY_PROMPT, _KNOWN_TYPES,
)

log = logging.getLogger("3ll.clm.doc_extractor")

# ── Doc type mapping — vault doc_type → scanner contract_type ────────────────
# Covers all 20 CON classes plus legacy and common alias forms.
_DOC_TYPE_MAP: dict[str, str] = {
    # Load-level
    "rate_con":                  "rate_confirmation",
    "rate_confirmation":         "rate_confirmation",
    "spot_rate_confirmation":    "rate_confirmation",
    "dedicated_lane_agreement":  "dedicated_lane_agreement",
    "dedicated_lane":            "dedicated_lane_agreement",
    # BOL / POD / Invoice
    "bol":                       "bol",
    "pod":                       "pod",
    "invoice":                   "invoice",
    # Agreement types (CON-01 through CON-09, CON-12)
    "agreement":                 "broker_carrier_agreement",
    "broker_agreement":          "broker_carrier_agreement",
    "broker_carrier_agreement":  "broker_carrier_agreement",
    "master_service_agreement":  "master_service_agreement",
    "msa":                       "master_service_agreement",
    "shipper_carrier_agreement": "shipper_carrier_agreement",
    "owner_operator_lease":      "owner_operator_lease",
    "ic_lease":                  "owner_operator_lease",
    "freight_brokerage_terms":   "freight_brokerage_terms",
    "co_brokerage_agreement":    "co_brokerage_agreement",
    "co_load":                   "co_brokerage_agreement",
    # Specialized addenda (CON-13, CON-14)
    "fuel_surcharge_addendum":   "fuel_surcharge_addendum",
    "fsc_addendum":              "fuel_surcharge_addendum",
    "hazmat_transport_rider":    "hazmat_transport_rider",
    "hazmat":                    "hazmat_transport_rider",
    # Intermodal / logistics (CON-06, CON-07, CON-10, CON-11, CON-16, CON-17, CON-18)
    "intermodal_agreement":      "intermodal_agreement",
    "intermodal":                "intermodal_agreement",
    "tpl_contract":              "tpl_contract",
    "3pl":                       "tpl_contract",
    "warehouse_bailment":        "warehouse_bailment",
    "warehouse":                 "warehouse_bailment",
    "trailer_interchange_agreement": "trailer_interchange_agreement",
    "trailer_interchange":       "trailer_interchange_agreement",
    "freight_forwarding_agreement":  "freight_forwarding_agreement",
    "freight_forwarding":        "freight_forwarding_agreement",
    "yard_management_contract":  "yard_management_contract",
    "yard_management":           "yard_management_contract",
    "logistics_tech_saas":       "logistics_tech_saas",
    "saas":                      "logistics_tech_saas",
    # Special purpose (CON-15, CON-19, CON-20)
    "cross_border_agreement":    "cross_border_agreement",
    "cross_border":              "cross_border_agreement",
    "cargo_claim_settlement":    "cargo_claim_settlement",
    "cargo_claim":               "cargo_claim_settlement",
    "nemt_contract":             "nemt_contract",
    "nemt":                      "nemt_contract",
    # Other / non-extractable — return None to trigger auto-classify
    "compliance":                None,
    "w9":                        None,
    "insurance":                 None,
    "other":                     None,
    "folder":                    None,
    "unknown":                   None,
}

# ── MIME type sets ────────────────────────────────────────────────────────────
_IMAGE_MIME_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp",
}
_HEIC_MIME_TYPES = {
    "image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence",
}
_PDF_MIME_TYPE = "application/pdf"

# Phone photos often exceed 20 MP — resize to this max dimension before sending
_MAX_PHOTO_DIMENSION = 3840


# ── File-type helpers ─────────────────────────────────────────────────────────

def _detect_mime_from_bytes(data: bytes) -> str:
    """Sniff MIME type from magic bytes when header metadata is missing."""
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] in (b"GIF8", b"GIF9"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    # HEIC/HEIF — ftyp box at offset 4
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heis", b"hevx", b"heim", b"hevm", b"hevc",
                     b"mif1", b"msf1", b"heix"):
            return "image/heic"
    return "application/octet-stream"


def _normalize_image(content: bytes, mime_type: str) -> tuple[bytes, str]:
    """Normalize any image (including HEIC/HEIF) to JPEG for Claude Vision.

    Applies EXIF orientation, resizes oversized phone photos, and converts
    HEIC/HEIF to JPEG. Returns (jpeg_bytes, "image/jpeg").
    """
    try:
        from PIL import Image, ImageOps  # noqa: PLC0415

        # Register HEIC support if available
        if mime_type in _HEIC_MIME_TYPES:
            try:
                import pillow_heif  # noqa: PLC0415
                pillow_heif.register_heif_opener()
            except ImportError:
                log.warning("pillow-heif not installed; HEIC conversion may fail")

        img = Image.open(io.BytesIO(content))

        # Fix EXIF orientation (phones rotate pixels in metadata, not file)
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Convert palette / RGBA modes for JPEG compatibility
        if img.mode in ("P", "RGBA", "LA", "L"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Resize if either dimension exceeds threshold
        w, h = img.size
        if max(w, h) > _MAX_PHOTO_DIMENSION:
            scale = _MAX_PHOTO_DIMENSION / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            log.info("doc_extractor: resized phone photo %dx%d → %dx%d", w, h, *img.size)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88, optimize=True)
        return buf.getvalue(), "image/jpeg"

    except Exception as exc:
        log.warning("Image normalization failed (%s): %s — sending raw", mime_type, exc)
        return content, mime_type if mime_type in _IMAGE_MIME_TYPES else "image/jpeg"


# ── Storage helpers ───────────────────────────────────────────────────────────

def _download_file(storage_path: str, bucket: str) -> bytes | None:
    buckets = [bucket, "documents", "driver-documents"]
    for b in dict.fromkeys(buckets):   # deduplicate, preserve order
        try:
            data = get_supabase().storage.from_(b).download(storage_path)
            return data if isinstance(data, bytes) else bytes(data)
        except Exception:
            continue
    return None


# ── PDF text extraction ───────────────────────────────────────────────────────

def _extract_text_from_pdf(content: bytes) -> str:
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


# ── Claude Vision helpers ─────────────────────────────────────────────────────

def _classify_with_vision(content: bytes, mime_type: str) -> str:
    """Ask Claude to identify the document type from an image/PDF.

    Returns a string like 'rate_confirmation', 'bol', 'invoice', etc.
    """
    import json  # noqa: PLC0415 — already imported at module level
    s = get_settings()
    client = anthropic.Anthropic(api_key=s.anthropic_api_key)

    b64 = base64.standard_b64encode(content).decode()
    if mime_type == _PDF_MIME_TYPE:
        source_block: dict = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
        }
    else:
        img_type = mime_type if mime_type in _IMAGE_MIME_TYPES else "image/jpeg"
        source_block = {
            "type": "image",
            "source": {"type": "base64", "media_type": img_type, "data": b64},
        }

    classify_prompt = _CLASSIFY_PROMPT.format(document_text="[See attached document above]")
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=64,
            system=_CLASSIFY_SYSTEM,
            messages=[{
                "role": "user",
                "content": [source_block, {"type": "text", "text": classify_prompt}],
            }],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        result = json.loads(text)
        doc_type = str(result.get("doc_type", "other")).lower().strip()
        log.info("_classify_with_vision → %s", doc_type)
        return doc_type
    except Exception as exc:
        log.warning("Vision classify failed: %s — defaulting to rate_confirmation", exc)
        return "rate_confirmation"


def _scan_with_claude_vision(
    content: bytes,
    mime_type: str,
    contract_type: str,
) -> tuple[dict[str, Any], float, list[str]]:
    """Send file bytes to Claude Vision and return (extracted, confidence, warnings)."""
    s = get_settings()
    client = anthropic.Anthropic(api_key=s.anthropic_api_key)

    # Normalize HEIC / HEIF and oversized phone photos before encoding
    if mime_type in _HEIC_MIME_TYPES or mime_type in _IMAGE_MIME_TYPES:
        content, mime_type = _normalize_image(content, mime_type)

    b64 = base64.standard_b64encode(content).decode()

    if mime_type == _PDF_MIME_TYPE:
        source_block: dict = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
        }
    else:
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
                "content": [source_block, {"type": "text", "text": text_prompt}],
            }],
        )
        content_text = message.content[0].text.strip()

        if content_text.startswith("```"):
            lines = content_text.split("\n")
            content_text = "\n".join(
                lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            )

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


# ── Public entry point ────────────────────────────────────────────────────────

def extract_vault_doc(doc_id: str) -> dict:
    """Run the full extraction pipeline on a vault document.

    Downloads from Supabase Storage, chooses the right extraction path,
    calls Claude, and persists results to document_vault.

    Returns a summary dict: {ok, doc_id, method, confidence, warnings, extracted}.
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
    raw_mime = (doc.get("mime_type") or "").lower().strip()
    doc_type = doc.get("doc_type") or "rate_con"
    contract_type = _DOC_TYPE_MAP.get(doc_type)  # None means auto-classify

    log.info("extract_vault_doc id=%s type=%s mime=%s auto_classify=%s",
             doc_id, doc_type, raw_mime, contract_type is None)

    # ── Download ──────────────────────────────────────────────────────────────
    content = _download_file(storage_path, bucket)
    if not content:
        return {"error": "Could not download file from storage", "doc_id": doc_id}

    # Sniff MIME if not set or generic
    mime_type = raw_mime if raw_mime and raw_mime != "application/octet-stream" else _detect_mime_from_bytes(content)

    log.info("extract_vault_doc resolved mime=%s for id=%s", mime_type, doc_id)

    # ── Choose extraction path ────────────────────────────────────────────────
    method = "claude_vision"
    extracted: dict[str, Any] = {}
    confidence = 0.0
    warnings: list[str] = []

    if mime_type == _PDF_MIME_TYPE:
        text = _extract_text_from_pdf(content)
        if len(text) > 100:
            from .scanner import scan_contract, classify_document_type  # noqa: PLC0415
            if not contract_type:
                contract_type = classify_document_type(text)
                log.info("extract_vault_doc auto-classified as %s", contract_type)
            extracted, confidence, warnings = scan_contract(text, contract_type)
            method = "pdf_text"
        else:
            # Scanned / image PDF — Vision API (classify visually if needed)
            if not contract_type:
                contract_type = _classify_with_vision(content, mime_type)
                log.info("extract_vault_doc vision-classified as %s", contract_type)
            extracted, confidence, warnings = _scan_with_claude_vision(content, mime_type, contract_type)
            method = "claude_vision_pdf"

    elif mime_type in _IMAGE_MIME_TYPES or mime_type in _HEIC_MIME_TYPES:
        # Normalize first so classify sees the final JPEG
        norm_content, norm_mime = _normalize_image(content, mime_type) if mime_type in _HEIC_MIME_TYPES else (content, mime_type)
        if not contract_type:
            contract_type = _classify_with_vision(norm_content, norm_mime)
            log.info("extract_vault_doc vision-classified as %s", contract_type)
        extracted, confidence, warnings = _scan_with_claude_vision(norm_content, norm_mime, contract_type)
        method = "claude_vision_heic" if mime_type in _HEIC_MIME_TYPES else "claude_vision"

    else:
        # Last resort — try decoding as UTF-8 text
        text = content.decode("utf-8", errors="ignore").strip()
        if len(text) > 100:
            from .scanner import scan_contract, classify_document_type  # noqa: PLC0415
            if not contract_type:
                contract_type = classify_document_type(text)
            extracted, confidence, warnings = scan_contract(text, contract_type)
            method = "pdf_text"
        else:
            sniffed = _detect_mime_from_bytes(content)
            final_mime = sniffed if sniffed != "application/octet-stream" else "image/jpeg"
            if not contract_type:
                contract_type = _classify_with_vision(content, final_mime)
            extracted, confidence, warnings = _scan_with_claude_vision(content, final_mime, contract_type)
            method = "claude_vision_fallback"

    contract_type = contract_type or "rate_confirmation"  # final safety fallback

    # ── Persist ───────────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    update_row: dict = {
        "extracted_data":     extracted,
        "extract_confidence": confidence,
        "extract_warnings":   warnings or [],
        "extracted_at":       now,
        "extract_method":     method,
    }
    # If we auto-classified an "other"/"unknown" doc, update the type in vault
    if doc_type in ("other", "unknown", None) and contract_type:
        update_row["doc_type"] = contract_type
    sb.table("document_vault").update(update_row).eq("id", doc_id).execute()

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


def extract_bytes(
    content: bytes,
    filename: str,
    contract_type: str = "rate_confirmation",
    mime_type: str | None = None,
) -> tuple[dict[str, Any], float, list[str]]:
    """Extract variables directly from in-memory bytes without a vault record.

    Used for upload-and-scan in a single request (no vault doc needed).
    Returns (extracted_vars, confidence, warnings).
    """
    if not mime_type:
        mime_type = _detect_mime_from_bytes(content)
        # Fallback: guess from filename extension
        if mime_type == "application/octet-stream":
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            mime_type = {
                "pdf": "application/pdf",
                "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "gif": "image/gif", "webp": "image/webp",
                "heic": "image/heic", "heif": "image/heif",
            }.get(ext, "application/octet-stream")

    # Resolve contract_type — auto-classify if caller passed None / "auto"
    auto_classify = not contract_type or contract_type == "auto"
    effective_type = contract_type if (contract_type and contract_type in _KNOWN_TYPES) else None

    log.info("extract_bytes filename=%s mime=%s type=%s auto_classify=%s",
             filename, mime_type, effective_type, auto_classify)

    if mime_type == _PDF_MIME_TYPE:
        text = _extract_text_from_pdf(content)
        if len(text) > 100:
            from .scanner import scan_contract, classify_document_type  # noqa: PLC0415
            if not effective_type:
                effective_type = classify_document_type(text)
                log.info("extract_bytes text-classified as %s", effective_type)
            return scan_contract(text, effective_type)
        # Scanned PDF — Vision
        if not effective_type:
            effective_type = _classify_with_vision(content, mime_type)
        return _scan_with_claude_vision(content, mime_type, effective_type)

    if mime_type in _HEIC_MIME_TYPES:
        norm_content, norm_mime = _normalize_image(content, mime_type)
        if not effective_type:
            effective_type = _classify_with_vision(norm_content, norm_mime)
        return _scan_with_claude_vision(norm_content, norm_mime, effective_type)

    if mime_type in _IMAGE_MIME_TYPES:
        if not effective_type:
            effective_type = _classify_with_vision(content, mime_type)
        return _scan_with_claude_vision(content, mime_type, effective_type)

    # Fallback: treat as text
    text = content.decode("utf-8", errors="ignore").strip()
    if len(text) > 100:
        from .scanner import scan_contract, classify_document_type  # noqa: PLC0415
        if not effective_type:
            effective_type = classify_document_type(text)
        return scan_contract(text, effective_type or "rate_confirmation")

    return {}, 0.0, [f"Could not extract content from file type: {mime_type}"]

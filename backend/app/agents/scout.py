"""Scout — Steps 27-28. Claude vision OCR + paperwork verification.

Supports two input modes:
  - image_url:   publicly accessible URL (Supabase Storage signed URL)
  - image_b64:   base64-encoded image string (from driver PWA upload)

Document types detected:
  - rate_confirmation, bol (bill of lading), pod (proof of delivery), invoice
"""
from __future__ import annotations

import base64
import re
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_MODEL = "claude-sonnet-4-6"

_OCR_PROMPT = """\
You are a freight document OCR specialist. Extract every field from this trucking document.

Return ONLY valid JSON — no markdown, no code fences, no explanation.

Extract these fields (use null for any field not found):
{
  "doc_type": "rate_confirmation | bol | pod | invoice | unknown",
  "load_number": null,
  "broker_name": null,
  "broker_mc": null,
  "broker_dot": null,
  "broker_ref_number": null,
  "shipper_name": null,
  "origin_address": null,
  "origin_city": null,
  "origin_state": null,
  "origin_zip": null,
  "consignee_name": null,
  "dest_address": null,
  "dest_city": null,
  "dest_state": null,
  "dest_zip": null,
  "pickup_date": null,
  "delivery_date": null,
  "commodity": null,
  "weight_lbs": null,
  "pieces": null,
  "rate_total": null,
  "rate_per_mile": null,
  "miles": null,
  "fuel_surcharge": null,
  "detention_rate": null,
  "payment_terms": null,
  "quick_pay_available": null,
  "driver_name": null,
  "driver_signature": null,
  "delivery_confirmed_at": null,
  "receiver_signature": null,
  "hazmat": false,
  "hazmat_class": null,
  "temperature_controlled": false,
  "temp_min_f": null,
  "temp_max_f": null,
  "special_instructions": null,
  "refs": []
}
"""


def _download_image_b64(url: str) -> tuple[str, str]:
    """Download image from URL and return (base64_data, media_type)."""
    resp = httpx.get(url, timeout=15, follow_redirects=True)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    if content_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        content_type = "image/jpeg"
    return base64.standard_b64encode(resp.content).decode(), content_type


def _call_claude_vision(image_b64: str, media_type: str) -> dict[str, Any]:
    """Send image to Claude vision API and parse the JSON response."""
    s = get_settings()
    if not s.anthropic_api_key:
        return {"error": "anthropic_not_configured"}

    payload = {
        "model": _MODEL,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": _OCR_PROMPT},
                ],
            }
        ],
    }

    resp = httpx.post(
        _ANTHROPIC_URL,
        headers={
            "x-api-key": s.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()

    text = resp.json()["content"][0]["text"].strip()
    # Strip any accidental markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    import json
    return json.loads(text)


def ocr_document(
    image_url: str | None = None,
    image_b64: str | None = None,
    media_type: str = "image/jpeg",
) -> dict[str, Any]:
    """Step 27: OCR a freight document via Claude vision.

    Pass either image_url (Supabase signed URL) or image_b64 (raw base64).
    Returns structured dict of extracted fields.
    """
    try:
        if image_url and not image_b64:
            image_b64, media_type = _download_image_b64(image_url)

        if not image_b64:
            return {"error": "no_image_provided"}

        return _call_claude_vision(image_b64, media_type)

    except httpx.HTTPStatusError as exc:
        return {"error": f"http_{exc.response.status_code}", "detail": exc.response.text[:200]}
    except httpx.RequestError as exc:
        return {"error": "network_error", "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": "ocr_failed", "detail": str(exc)}


def verify(extracted: dict[str, Any], expected: dict[str, Any] | None = None) -> dict[str, Any]:
    """Step 28: cross-check extracted fields against the booked load record."""
    issues: list[str] = []
    expected = expected or {}

    if not extracted.get("rate_total"):
        issues.append("rate_not_detected")

    if not extracted.get("origin_city"):
        issues.append("origin_not_detected")

    if not extracted.get("dest_city"):
        issues.append("destination_not_detected")

    broker_mc = str(extracted.get("broker_mc") or "").strip()
    exp_broker_mc = str(expected.get("broker_mc") or "").strip()
    if broker_mc and exp_broker_mc and broker_mc != exp_broker_mc:
        issues.append("broker_mc_mismatch")

    load_number = str(extracted.get("load_number") or "").strip()
    exp_load = str(expected.get("load_number") or "").strip()
    if load_number and exp_load and load_number != exp_load:
        issues.append("load_number_mismatch")

    rate = extracted.get("rate_total")
    exp_rate = expected.get("rate_total")
    if rate and exp_rate:
        try:
            if abs(float(rate) - float(exp_rate)) > 1.0:
                issues.append("rate_mismatch")
        except (ValueError, TypeError):
            pass

    return {"ok": not issues, "issues": issues, "issue_count": len(issues)}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Agent entrypoint — OCR a document and optionally verify against a load."""
    file_ref = payload.get("file_ref") or payload.get("image_url")
    image_b64 = payload.get("image_b64")
    media_type = payload.get("media_type", "image/jpeg")

    log_agent("scout", "ocr_start", payload={"file": file_ref or "b64_upload"})

    extracted = ocr_document(
        image_url=file_ref,
        image_b64=image_b64,
        media_type=media_type,
    )

    if "error" in extracted:
        log_agent("scout", "ocr_failed", error=extracted["error"])
        return {"agent": "scout", "status": "failed", "error": extracted["error"]}

    verification = verify(extracted, expected=payload.get("expected"))

    log_agent("scout", "ocr_complete",
              payload={"doc_type": extracted.get("doc_type"), "issues": verification["issues"]},
              result="ok" if verification["ok"] else "issues_found")

    return {
        "agent": "scout",
        "status": "ok" if verification["ok"] else "issues_found",
        "doc_type": extracted.get("doc_type"),
        "extracted": extracted,
        "verification": verification,
    }

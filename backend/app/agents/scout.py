"""Scout — Steps 27-28. Google Vision OCR + paperwork verification."""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent


def ocr_document(image_url_or_bytes: Any) -> dict[str, Any]:
    """Step 27: call Google Vision on a BOL/Rate Con. Stub returns schema."""
    # TODO: google-cloud-vision ImageAnnotatorClient.document_text_detection
    return {
        "origin": None, "destination": None, "rate_total": None,
        "commodity": None, "weight_lbs": None, "broker_mc": None,
        "pickup_at": None, "delivery_at": None, "refs": [],
    }


def verify(extracted: dict[str, Any], expected_broker: str | None = None) -> dict[str, Any]:
    """Step 28: compare OCR against the booked load."""
    issues: list[str] = []
    if expected_broker and extracted.get("broker_mc") and expected_broker != extracted["broker_mc"]:
        issues.append("broker_mc_mismatch")
    if not extracted.get("rate_total"):
        issues.append("rate_not_detected")
    return {"ok": not issues, "issues": issues}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    log_agent("scout", "ocr", payload={"file": payload.get("file_ref")}, result="stub")
    return {"agent": "scout", "status": "stub", "extracted": ocr_document(None)}

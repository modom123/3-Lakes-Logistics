"""Signal — Step 34. Emergency 800-number routing."""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent

EMERGENCY_KEYWORDS = {
    "breakdown", "accident", "crash", "dot", "inspection", "stop",
    "injury", "fuel out", "locked out", "hijack",
}


def classify(call_transcript: str) -> str:
    text = (call_transcript or "").lower()
    if any(kw in text for kw in EMERGENCY_KEYWORDS):
        return "emergency"
    if "dispatch" in text or "load" in text:
        return "dispatch"
    return "general"


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = classify(payload.get("transcript", ""))
    log_agent("signal", "classify", payload={"kind": kind}, result=kind)
    # TODO: escalate via Twilio SMS to Commander if emergency
    return {"agent": "signal", "routing": kind}

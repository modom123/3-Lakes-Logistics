"""Echo — Step 36. Driver SMS liaison."""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent


QUICK_ANSWERS = {
    "pay": "Your weekly pay drops Friday by 8pm CT. Text PAY DETAIL for a breakdown.",
    "hos": "You can check live HOS in the driver app under Status.",
    "fuel": "Fuel card issues? Text FUEL HELP and a dispatcher will call within 10 min.",
    "load": "Next load appears in the driver app. Text LOAD for the current assignment.",
}


def reply_to(driver_code: str, msg: str) -> str:
    key = msg.strip().lower().split()[0] if msg else ""
    if key in QUICK_ANSWERS:
        return QUICK_ANSWERS[key]
    return "Got it — passing this to a dispatcher. You'll hear back shortly."


def run(payload: dict[str, Any]) -> dict[str, Any]:
    reply = reply_to(payload.get("driver_code", ""), payload.get("message", ""))
    log_agent("echo", "sms_reply", payload={"driver": payload.get("driver_code")}, result="composed")
    return {"agent": "echo", "reply": reply}

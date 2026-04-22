"""Echo — Inbound comms triage (step 69)."""
from __future__ import annotations

from typing import Any

from ..integrations.sms import handle_inbound, send_sms
from ..logging_service import log_agent
from .nova import open_thread

QUICK_ANSWERS = {
    "pay":  "Your weekly pay drops Friday by 8pm CT. Text PAY DETAIL for a breakdown.",
    "hos":  "You can check live HOS in the driver app under Status.",
    "fuel": "Fuel card issues? Text FUEL HELP and a dispatcher will call within 10 min.",
    "load": "Next load appears in the driver app. Text LOAD for the current assignment.",
}


def reply_to(msg: str) -> str:
    key = msg.strip().lower().split()[0] if msg else ""
    return QUICK_ANSWERS.get(
        key, "Got it — passing this to a dispatcher. You'll hear back shortly."
    )


def triage_sms(from_phone: str, body: str, carrier_id: str | None = None,
               driver_id: str | None = None) -> dict[str, Any]:
    kind = handle_inbound(from_phone, body)
    if kind == "opted_out":
        return {"status": "ok", "routed": "opt_out"}
    auto = reply_to(body)
    send_sms(from_phone, auto, carrier_id=carrier_id)
    if not any(k in body.lower() for k in QUICK_ANSWERS):
        open_thread(
            carrier_id=carrier_id, driver_id=driver_id,
            channel="sms", subject=None, first_message=body, author=from_phone,
        )
    return {"status": "ok", "routed": "auto_reply", "reply": auto}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind") or "triage_sms"
    if kind == "triage_sms":
        return {"agent": "echo", **triage_sms(
            payload.get("from") or "", payload.get("body") or "",
            carrier_id=payload.get("carrier_id"),
            driver_id=payload.get("driver_id"),
        )}
    reply = reply_to(payload.get("message", ""))
    log_agent("echo", "sms_reply", result="composed")
    return {"agent": "echo", "status": "ok", "reply": reply}

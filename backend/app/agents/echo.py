"""Echo — Step 36. Driver SMS liaison — receives inbound texts and replies via Twilio."""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from .signal import _send_sms  # reuse Twilio send helper

QUICK_ANSWERS = {
    "pay": (
        "Your weekly pay drops Friday by 8pm CT. "
        "Text PAY DETAIL for a full breakdown or call dispatch at (800) 3-LAKES-1."
    ),
    "hos": (
        "You can check live HOS in your driver app under Status. "
        "Text HOS HELP if you need an exception logged."
    ),
    "fuel": (
        "Fuel card issues? Text FUEL HELP and a dispatcher will call within 10 min. "
        "Emergency fuel: (800) 3-LAKES-1."
    ),
    "load": (
        "Your next load appears in the driver app. "
        "Text LOAD for your current assignment details."
    ),
    "load detail": "Fetching your load details — check driver app or call (800) 3-LAKES-1.",
    "pay detail": "Your pay breakdown is available in the driver app under Settlements.",
    "hos help": "Dispatching a supervisor to help with your HOS log. Expect a call shortly.",
    "fuel help": "Routing your fuel card issue to fleet ops — expect a call in 10 min.",
    "breakdown": "Marking you for roadside assistance — dispatching help now. Stay safe.",
    "emergency": "Alerting dispatch NOW. Stay on the line or call 911 if life-threatening.",
}

_DEFAULT_REPLY = (
    "Got it — passing this to a dispatcher. You'll hear back shortly. "
    "Urgent? Call (800) 3-LAKES-1."
)


def reply_to(driver_code: str, msg: str) -> str:
    key = (msg or "").strip().lower()
    # Check full phrase first, then first word
    if key in QUICK_ANSWERS:
        return QUICK_ANSWERS[key]
    first_word = key.split()[0] if key else ""
    return QUICK_ANSWERS.get(first_word, _DEFAULT_REPLY)


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Compose and send an SMS reply to a driver inbound message."""
    driver_code = payload.get("driver_code", "")
    msg = payload.get("message", "")
    driver_phone = payload.get("driver_phone", "")
    carrier_id = payload.get("carrier_id", "")

    reply = reply_to(driver_code, msg)

    sms_result: dict[str, Any] = {"status": "not_sent"}
    if driver_phone:
        sms_result = _send_sms(driver_phone, reply, carrier_id=carrier_id)
    else:
        log_agent("echo", "no_phone", carrier_id=carrier_id,
                  payload={"driver_code": driver_code}, result="skipped")

    log_agent("echo", "sms_reply", carrier_id=carrier_id,
              payload={"driver": driver_code, "keyword": msg[:30]},
              result=sms_result.get("status", "composed"))

    return {
        "agent": "echo",
        "driver_code": driver_code,
        "reply": reply,
        "sms": sms_result,
    }

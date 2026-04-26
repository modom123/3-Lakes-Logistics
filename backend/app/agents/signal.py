"""Signal — Step 34. Emergency routing + Twilio SMS dispatcher.

Handles all outbound SMS alerts:
  - emergency:    accident / breakdown / DOT stop → Commander on-call
  - hos_warning:  driver approaching HOS limit
  - cdl_alert:    CDL or medical card expiry warning
  - breakdown:    mechanical failure — roadside assistance
  - dispatch:     load assigned confirmation to driver
  - check_call:   quick status ping to broker
"""
from __future__ import annotations

from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings

_TWILIO_BASE = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

EMERGENCY_KEYWORDS = {
    "breakdown", "accident", "crash", "dot", "inspection", "stop",
    "injury", "fuel out", "locked out", "hijack", "rollover", "fire",
}

# ── SMS templates ─────────────────────────────────────────────────────────────

_MSGS: dict[str, str] = {
    "emergency": (
        "🚨 3LL EMERGENCY — {driver_name} | Load #{load_number}\n"
        "Type: {incident_type}\n"
        "Location: {location}\n"
        "Driver: {driver_phone}\n"
        "Call immediately."
    ),
    "hos_warning": (
        "⚠️ HOS WARNING — {driver_name}\n"
        "Load #{load_number} | {hours_remaining}h remaining\n"
        "Current location: {location}\n"
        "ETA to delivery: {eta}"
    ),
    "cdl_alert": (
        "📋 CDL ALERT — {driver_name}\n"
        "CDL #{cdl_number} expires {expiry_date} ({days_left} days)\n"
        "Carrier: {carrier_name}\n"
        "Action required — renew before expiry."
    ),
    "breakdown": (
        "🔧 BREAKDOWN — {driver_name} | Load #{load_number}\n"
        "Location: {location}\n"
        "Issue: {issue}\n"
        "Driver: {driver_phone}\n"
        "Dispatch roadside assistance."
    ),
    "dispatch": (
        "✅ DISPATCHED — Load #{load_number}\n"
        "{origin} → {dest}\n"
        "Pickup: {pickup_dt}\n"
        "Rate: ${rate_total}\n"
        "Reply CONFIRM to accept."
    ),
    "check_call": (
        "3LL Update — Load #{load_number}\n"
        "Status: {status}\n"
        "Location: {current_location}\n"
        "ETA: {eta}"
    ),
}


# ── Core send helper ──────────────────────────────────────────────────────────

def _send_sms(to_number: str, body: str, carrier_id: str = "") -> dict[str, Any]:
    """POST an SMS via Twilio REST API."""
    s = get_settings()

    if not all([s.twilio_account_sid, s.twilio_auth_token, s.twilio_from_number]):
        log_agent("signal", "sms_skipped", carrier_id=carrier_id,
                  payload={"reason": "twilio_not_configured", "to": to_number})
        return {"status": "skipped", "reason": "twilio_not_configured"}

    if not to_number:
        return {"status": "skipped", "reason": "no_destination_number"}

    url = _TWILIO_BASE.format(sid=s.twilio_account_sid)
    try:
        resp = httpx.post(
            url,
            auth=(s.twilio_account_sid, s.twilio_auth_token),
            data={"From": s.twilio_from_number, "To": to_number, "Body": body},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        sid = data.get("sid", "")
        log_agent("signal", "sms_sent", carrier_id=carrier_id,
                  payload={"to": to_number, "sid": sid})
        return {"status": "sent", "sid": sid, "to": to_number}

    except httpx.HTTPStatusError as exc:
        err = f"HTTP {exc.response.status_code}: {exc.response.text}"
        log_agent("signal", "sms_failed", carrier_id=carrier_id, error=err)
        return {"status": "failed", "error": err}

    except httpx.RequestError as exc:
        log_agent("signal", "sms_failed", carrier_id=carrier_id, error=str(exc))
        return {"status": "failed", "error": str(exc)}


# ── Call classifier ───────────────────────────────────────────────────────────

def classify(call_transcript: str) -> str:
    text = (call_transcript or "").lower()
    if any(kw in text for kw in EMERGENCY_KEYWORDS):
        return "emergency"
    if "dispatch" in text or "load" in text:
        return "dispatch"
    return "general"


# ── SMS composers ─────────────────────────────────────────────────────────────

def send_emergency(payload: dict[str, Any]) -> dict[str, Any]:
    """Alert Commander on-call + carrier safety contact."""
    s = get_settings()
    body = _MSGS["emergency"].format(
        driver_name=payload.get("driver_name", "Unknown"),
        load_number=payload.get("load_number", ""),
        incident_type=payload.get("incident_type", "Emergency"),
        location=payload.get("location", "Unknown location"),
        driver_phone=payload.get("driver_phone", "on file"),
    )
    results = []
    # Primary: 3LL Commander on-call (VAPI/operations number)
    commander_number = payload.get("commander_number") or s.twilio_from_number
    results.append(_send_sms(commander_number, body, payload.get("carrier_id", "")))

    # Secondary: carrier safety contact if provided
    safety_number = payload.get("safety_phone", "")
    if safety_number and safety_number != commander_number:
        results.append(_send_sms(safety_number, body, payload.get("carrier_id", "")))

    return {"status": "sent" if any(r["status"] == "sent" for r in results) else "failed",
            "recipients": results}


def send_hos_warning(payload: dict[str, Any]) -> dict[str, Any]:
    body = _MSGS["hos_warning"].format(
        driver_name=payload.get("driver_name", "Driver"),
        load_number=payload.get("load_number", ""),
        hours_remaining=payload.get("hours_remaining", ""),
        location=payload.get("location", "en route"),
        eta=payload.get("eta", "unknown"),
    )
    to = payload.get("dispatcher_phone") or payload.get("commander_phone", "")
    return _send_sms(to, body, payload.get("carrier_id", ""))


def send_cdl_alert(payload: dict[str, Any]) -> dict[str, Any]:
    body = _MSGS["cdl_alert"].format(
        driver_name=payload.get("driver_name", ""),
        cdl_number=payload.get("cdl_number", ""),
        expiry_date=payload.get("expiry_date", ""),
        days_left=payload.get("days_left", ""),
        carrier_name=payload.get("carrier_name", ""),
    )
    to = payload.get("carrier_phone") or payload.get("dispatcher_phone", "")
    return _send_sms(to, body, payload.get("carrier_id", ""))


def send_breakdown(payload: dict[str, Any]) -> dict[str, Any]:
    body = _MSGS["breakdown"].format(
        driver_name=payload.get("driver_name", "Driver"),
        load_number=payload.get("load_number", ""),
        location=payload.get("location", "Unknown location"),
        issue=payload.get("issue", "mechanical failure"),
        driver_phone=payload.get("driver_phone", "on file"),
    )
    to = payload.get("dispatcher_phone") or payload.get("commander_phone", "")
    return _send_sms(to, body, payload.get("carrier_id", ""))


def send_dispatch_sms(payload: dict[str, Any]) -> dict[str, Any]:
    origin = f"{payload.get('origin_city', '')}, {payload.get('origin_state', '')}"
    dest = f"{payload.get('dest_city', '')}, {payload.get('dest_state', '')}"
    body = _MSGS["dispatch"].format(
        load_number=payload.get("load_number", ""),
        origin=origin,
        dest=dest,
        pickup_dt=payload.get("pickup_dt", ""),
        rate_total=payload.get("rate_total", ""),
    )
    to = payload.get("driver_phone", "")
    return _send_sms(to, body, payload.get("carrier_id", ""))


def send_check_call_sms(payload: dict[str, Any]) -> dict[str, Any]:
    body = _MSGS["check_call"].format(
        load_number=payload.get("load_number", ""),
        status=payload.get("status", "in transit").replace("_", " ").title(),
        current_location=payload.get("current_location", "en route"),
        eta=payload.get("eta", "on schedule"),
    )
    to = payload.get("broker_phone", "")
    return _send_sms(to, body, payload.get("carrier_id", ""))


# ── Agent entrypoint ──────────────────────────────────────────────────────────

_ACTIONS = {
    "emergency": send_emergency,
    "hos_warning": send_hos_warning,
    "cdl_alert": send_cdl_alert,
    "breakdown": send_breakdown,
    "dispatch": send_dispatch_sms,
    "check_call": send_check_call_sms,
}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Agent entrypoint — classify transcript or route by explicit action."""
    action = payload.get("action")

    # Auto-classify from voice transcript if no explicit action given
    if not action and payload.get("transcript"):
        kind = classify(payload["transcript"])
        log_agent("signal", "classify", payload={"kind": kind},
                  carrier_id=payload.get("carrier_id", ""), result=kind)
        if kind == "emergency":
            action = "emergency"
        else:
            return {"agent": "signal", "routing": kind, "sms": {"status": "not_required"}}

    if not action:
        return {"agent": "signal", "error": f"action required. Valid: {list(_ACTIONS)}"}

    handler = _ACTIONS.get(action)
    if not handler:
        return {"agent": "signal", "error": f"unknown action '{action}'. Valid: {list(_ACTIONS)}"}

    result = handler(payload)
    log_agent("signal", action, carrier_id=payload.get("carrier_id", ""),
              payload={"action": action}, result=result.get("status"))

    return {"agent": "signal", "action": action, "sms": result}

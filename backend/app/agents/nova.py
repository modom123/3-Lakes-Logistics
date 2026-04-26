"""Nova — transactional email agent.

Handles all outbound emails via Postmark:
  - welcome:     new carrier onboarding
  - dispatch:    load dispatch sheet to driver + broker
  - settlement:  weekly driver pay statement
  - check_call:  broker load status update
  - compliance:  CDL / insurance expiry alert
"""
from __future__ import annotations

from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings

_POSTMARK_URL = "https://api.postmarkapp.com/email"

# ── Email templates ───────────────────────────────────────────────────────────

_WELCOME_SUBJECT = "Welcome to 3 Lakes Logistics — Your Account is Active"
_WELCOME_BODY = """\
Hi {contact_name},

Welcome to 3 Lakes Logistics! Your carrier account has been set up and you're
ready to start moving freight.

Your carrier code: {carrier_code}
Dispatch line:     (800) 3-LAKES-1
Driver app:        https://app.3lakeslogistics.com/driver-pwa/

Your first load offer will come through within 24 hours of completing setup.
Reply to this email with any questions.

— 3 Lakes Logistics Ops Team
"""

_DISPATCH_SUBJECT = "DISPATCHED — Load {load_number} | {origin} → {dest}"
_DISPATCH_BODY = """\
{driver_name},

You have been dispatched on the following load:

  Load #:       {load_number}
  Broker:       {broker_name}
  Origin:       {origin_address}
  Destination:  {dest_address}
  Pickup:       {pickup_dt}
  Delivery:     {delivery_dt}
  Rate:         ${rate_total:.2f}

Commodity:  {commodity}
Weight:     {weight} lbs
Miles:      {miles}

BROKER CONTACT
  {broker_contact} — {broker_phone}
  Reference: {broker_ref_number}

Pick up a BOL at origin, photograph it, and upload in your driver app.
Safe travels.

— 3 Lakes Logistics Dispatch
"""

_SETTLEMENT_SUBJECT = "Settlement Statement — Week of {week_start}"
_SETTLEMENT_BODY = """\
{driver_name},

Here is your settlement statement for the week of {week_start} – {week_end}.

LOADS DELIVERED:   {loads_delivered}
TOTAL MILES:       {total_miles}

  Gross freight:        ${gross_rate:.2f}
  Driver share ({driver_pct}%): ${driver_gross:.2f}
  Fuel advances:       -${fuel_advances:.2f}
  Escrow deduction:    -${escrow_deduction:.2f}
  Lumper reimbursed:   +${lumper_reimbursements:.2f}
  Detention pay:       +${detention_pay:.2f}
  ─────────────────────────────────
  NET PAY:              ${net_pay:.2f}

Payment has been initiated to your bank account on file.
Funds typically arrive within 1–2 business days.

Questions? Reply to this email or call dispatch at (800) 3-LAKES-1.

— 3 Lakes Logistics Settlement Dept.
"""

_CHECK_CALL_SUBJECT = "Load {load_number} Status Update — {status}"
_CHECK_CALL_BODY = """\
Hi {broker_name},

Quick update on load {load_number} ({origin} → {dest}):

  Status:   {status}
  Location: {current_location}
  ETA:      {eta}
  Driver:   {driver_name} ({driver_phone})

Reach out anytime.

— 3 Lakes Logistics Dispatch
"""

_COMPLIANCE_SUBJECT = "[ACTION REQUIRED] {alert_type} — {driver_name}"
_COMPLIANCE_BODY = """\
Hi {contact_name},

This is an automated compliance alert from 3 Lakes Logistics.

Driver:     {driver_name}
CDL #:      {cdl_number}
Alert:      {alert_type}
Details:    {details}
Expiry:     {expiry_date}
Days Left:  {days_left}

{action_required}

Log in to the ops dashboard to manage compliance records:
  https://app.3lakeslogistics.com

— 3 Lakes Logistics Compliance System
"""


# ── Core send helper ──────────────────────────────────────────────────────────

def _send(to_email: str, subject: str, body: str, carrier_id: str = "") -> dict[str, Any]:
    """POST a plain-text email via the Postmark API. Returns status dict."""
    s = get_settings()

    if not s.postmark_server_token:
        log_agent("nova", "email_skipped", carrier_id=carrier_id,
                  payload={"reason": "postmark_not_configured", "to": to_email})
        return {"status": "skipped", "reason": "postmark_not_configured"}

    try:
        resp = httpx.post(
            _POSTMARK_URL,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": s.postmark_server_token,
            },
            json={
                "From": s.postmark_from_email,
                "To": to_email,
                "Subject": subject,
                "TextBody": body,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        msg_id = data.get("MessageID", "")
        log_agent("nova", "email_sent", carrier_id=carrier_id,
                  payload={"to": to_email, "subject": subject, "message_id": msg_id})
        return {"status": "sent", "message_id": msg_id, "to": to_email}

    except httpx.HTTPStatusError as exc:
        err = f"HTTP {exc.response.status_code}: {exc.response.text}"
        log_agent("nova", "email_failed", carrier_id=carrier_id, error=err)
        return {"status": "failed", "error": err}

    except httpx.RequestError as exc:
        log_agent("nova", "email_failed", carrier_id=carrier_id, error=str(exc))
        return {"status": "failed", "error": str(exc)}


# ── Email composers ───────────────────────────────────────────────────────────

def send_welcome(payload: dict[str, Any]) -> dict[str, Any]:
    to = payload.get("email", "")
    if not to:
        return {"status": "skipped", "reason": "no_email"}
    subject = _WELCOME_SUBJECT
    body = _WELCOME_BODY.format(
        contact_name=payload.get("contact_name", "there"),
        carrier_code=payload.get("carrier_code", "pending"),
    )
    return _send(to, subject, body, carrier_id=payload.get("carrier_id", ""))


def send_dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    to = payload.get("driver_email", "")
    if not to:
        return {"status": "skipped", "reason": "no_driver_email"}

    origin = f"{payload.get('origin_city', '')}, {payload.get('origin_state', '')}"
    dest = f"{payload.get('dest_city', '')}, {payload.get('dest_state', '')}"
    subject = _DISPATCH_SUBJECT.format(
        load_number=payload.get("load_number", ""),
        origin=origin,
        dest=dest,
    )
    body = _DISPATCH_BODY.format(
        driver_name=payload.get("driver_name", "Driver"),
        load_number=payload.get("load_number", ""),
        broker_name=payload.get("broker_name", ""),
        origin_address=payload.get("origin_address", origin),
        dest_address=payload.get("dest_address", dest),
        pickup_dt=payload.get("pickup_dt", ""),
        delivery_dt=payload.get("delivery_dt", ""),
        rate_total=float(payload.get("rate_total", 0)),
        commodity=payload.get("commodity", "General Freight"),
        weight=payload.get("weight", ""),
        miles=payload.get("miles", ""),
        broker_contact=payload.get("broker_contact", ""),
        broker_phone=payload.get("broker_phone", ""),
        broker_ref_number=payload.get("broker_ref_number", ""),
    )
    return _send(to, subject, body, carrier_id=payload.get("carrier_id", ""))


def send_settlement(payload: dict[str, Any]) -> dict[str, Any]:
    to = payload.get("driver_email", "")
    if not to:
        return {"status": "skipped", "reason": "no_driver_email"}

    s = payload.get("settlement", payload)
    driver_pct_display = int(float(s.get("driver_pct", 0.72)) * 100)
    subject = _SETTLEMENT_SUBJECT.format(week_start=s.get("week", ["", ""])[0])
    body = _SETTLEMENT_BODY.format(
        driver_name=payload.get("driver_name", "Driver"),
        week_start=s.get("week", ["", ""])[0],
        week_end=s.get("week", ["", ""])[1],
        loads_delivered=s.get("loads_delivered", 0),
        total_miles=s.get("total_miles", 0),
        gross_rate=float(s.get("gross_rate", 0)),
        driver_pct=driver_pct_display,
        driver_gross=float(s.get("driver_gross", 0)),
        fuel_advances=float(s.get("fuel_advances", 0)),
        escrow_deduction=float(s.get("escrow_deduction", 0)),
        lumper_reimbursements=float(s.get("lumper_reimbursements", 0)),
        detention_pay=float(s.get("detention_pay", 0)),
        net_pay=float(s.get("net_pay", 0)),
    )
    return _send(to, subject, body, carrier_id=payload.get("carrier_id", ""))


def send_check_call(payload: dict[str, Any]) -> dict[str, Any]:
    to = payload.get("broker_email", "")
    if not to:
        return {"status": "skipped", "reason": "no_broker_email"}

    origin = f"{payload.get('origin_city', '')}, {payload.get('origin_state', '')}"
    dest = f"{payload.get('dest_city', '')}, {payload.get('dest_state', '')}"
    subject = _CHECK_CALL_SUBJECT.format(
        load_number=payload.get("load_number", ""),
        status=payload.get("status", "in_transit").replace("_", " ").title(),
    )
    body = _CHECK_CALL_BODY.format(
        broker_name=payload.get("broker_name", "there"),
        load_number=payload.get("load_number", ""),
        origin=origin,
        dest=dest,
        status=payload.get("status", "in_transit").replace("_", " ").title(),
        current_location=payload.get("current_location", "en route"),
        eta=payload.get("eta", "on schedule"),
        driver_name=payload.get("driver_name", "on file"),
        driver_phone=payload.get("driver_phone", ""),
    )
    return _send(to, subject, body, carrier_id=payload.get("carrier_id", ""))


def send_compliance_alert(payload: dict[str, Any]) -> dict[str, Any]:
    to = payload.get("contact_email", "")
    if not to:
        return {"status": "skipped", "reason": "no_contact_email"}

    days_left = payload.get("days_left", 0)
    alert_type = payload.get("alert_type", "Compliance Alert")
    if days_left <= 7:
        action = "URGENT: This driver must be placed out-of-service immediately until resolved."
    elif days_left <= 30:
        action = "Schedule renewal now to avoid service interruption."
    else:
        action = "Please renew this document before expiry."

    subject = _COMPLIANCE_SUBJECT.format(
        alert_type=alert_type,
        driver_name=payload.get("driver_name", "Unknown Driver"),
    )
    body = _COMPLIANCE_BODY.format(
        contact_name=payload.get("contact_name", "Fleet Manager"),
        driver_name=payload.get("driver_name", ""),
        cdl_number=payload.get("cdl_number", ""),
        alert_type=alert_type,
        details=payload.get("details", ""),
        expiry_date=payload.get("expiry_date", ""),
        days_left=days_left,
        action_required=action,
    )
    return _send(to, subject, body, carrier_id=payload.get("carrier_id", ""))


# ── Agent entrypoint ──────────────────────────────────────────────────────────

_ACTIONS = {
    "welcome": send_welcome,
    "dispatch": send_dispatch,
    "settlement": send_settlement,
    "check_call": send_check_call,
    "compliance": send_compliance_alert,
}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Agent entrypoint — routes to the correct email composer by action type."""
    action = payload.get("action", "check_call")
    handler = _ACTIONS.get(action)

    if not handler:
        return {"agent": "nova", "error": f"unknown action '{action}'. Valid: {list(_ACTIONS)}"}

    result = handler(payload)
    log_agent("nova", action, carrier_id=payload.get("carrier_id", ""),
              payload={"to": payload.get("driver_email") or payload.get("broker_email") or payload.get("email")},
              result=result.get("status"))

    return {"agent": "nova", "action": action, "email": result}

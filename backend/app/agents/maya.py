"""Maya — Light Fleet Driver Intake & Onboarding.

Actions:
  process_intake   evaluate a submitted driver intake form → approve or deny
  welcome          send welcome SMS + next-steps to an approved driver
  deny             send rejection SMS + reason to a denied driver
  status           intake queue stats
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem

_NAME = "maya"

_WELCOME_SMS = (
    "Welcome to 3 Lakes Light Fleet! 🎉 Your account is approved. "
    "Download the driver app and you'll receive your first trip dispatch within 24 hours. "
    "Questions? Call 661-466-9932."
)

_DENY_RECORD_SMS = (
    "Thank you for your interest in 3 Lakes Light Fleet. "
    "Unfortunately we require a clean driving record to join our platform at this time. "
    "You're welcome to reapply if your record changes. — 3 Lakes Logistics"
)

_DENY_INSURANCE_SMS = (
    "Thank you for your interest in 3 Lakes Light Fleet. "
    "Active vehicle insurance is required before we can activate your account. "
    "Get covered and reapply at 3lakeslogistics.com. — 3 Lakes Logistics"
)


def _db():
    try:
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_phone(phone: str) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def _send_sms(phone: str, message: str) -> bool:
    """Send SMS via Bland AI or Twilio. Stub logs for now."""
    import logging
    logging.getLogger("3ll.maya").info("SMS → %s: %s", phone, message[:80])
    return True


def process_intake(payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate an intake submission and write the driver row if approved."""
    name = str(payload.get("name", "")).strip()
    phone = _normalize_phone(payload.get("phone") or "")
    email = str(payload.get("email", "")).strip().lower()
    location = str(payload.get("location", "")).strip()
    vehicle_year = payload.get("vehicle_year")
    vehicle_make = str(payload.get("vehicle_make", "")).strip()
    vehicle_model = str(payload.get("vehicle_model", "")).strip()
    vehicle_type = str(payload.get("vehicle_type", "")).strip()
    services = payload.get("approved_services") or []
    clean_record = str(payload.get("clean_record", "")).lower()
    has_insurance = str(payload.get("has_insurance", "")).lower()
    referral_source = payload.get("referral_source") or ""
    notes = payload.get("notes") or ""

    # Hard denials
    if clean_record == "no":
        log_agent(_NAME, "deny_record", payload={"name": name, "phone": phone})
        return {"approved": False, "reason": "dirty_record", "driver_id": None}

    if has_insurance == "no":
        log_agent(_NAME, "deny_insurance", payload={"name": name, "phone": phone})
        return {"approved": False, "reason": "no_insurance", "driver_id": None}

    if not name or not phone or not email:
        return {"approved": False, "reason": "missing_required_fields", "driver_id": None}

    sb = _db()
    driver_id = None

    if sb:
        try:
            result = sb.table("light_vehicle_drivers").insert({
                "name": name,
                "phone": phone,
                "email": email,
                "location": location,
                "vehicle_year": int(vehicle_year) if vehicle_year else None,
                "vehicle_make": vehicle_make,
                "vehicle_model": vehicle_model,
                "vehicle_type": vehicle_type,
                "approved_services": services,
                "clean_record": True,
                "has_insurance": True,
                "referral_source": referral_source,
                "notes": notes,
                "status": "active",
                "onboarded_at": _now(),
            }).execute()
            driver_id = (result.data[0] or {}).get("id") if result.data else None
        except Exception as e:  # noqa: BLE001
            log_agent(_NAME, "db_error", error=str(e))

    mem.remember(
        _NAME, "last_intake",
        {"name": name, "phone": phone, "driver_id": str(driver_id), "services": services},
        confidence=0.9,
        summary=f"Approved driver: {name} ({', '.join(services)})",
    )
    log_agent(_NAME, "approved", payload={"name": name, "services": services}, result=str(driver_id))

    return {
        "approved": True,
        "driver_id": str(driver_id) if driver_id else None,
        "name": name,
        "phone": phone,
        "services": services,
    }


def welcome(driver_id: str, phone: str, name: str) -> dict[str, Any]:
    normalized = _normalize_phone(phone)
    if not normalized:
        return {"sms_sent": False, "reason": "invalid_phone"}
    sent = _send_sms(normalized, _WELCOME_SMS)
    log_agent(_NAME, "welcome_sms", payload={"driver_id": driver_id, "name": name})
    return {"sms_sent": sent, "driver_id": driver_id, "phone": normalized}


def deny(phone: str, reason: str) -> dict[str, Any]:
    normalized = _normalize_phone(phone)
    if not normalized:
        return {"sms_sent": False, "reason": "invalid_phone"}
    msg = _DENY_RECORD_SMS if reason == "dirty_record" else _DENY_INSURANCE_SMS
    sent = _send_sms(normalized, msg)
    log_agent(_NAME, "deny_sms", payload={"phone": normalized, "reason": reason})
    return {"sms_sent": sent, "phone": normalized, "reason": reason}


def intake_stats() -> dict[str, Any]:
    sb = _db()
    if not sb:
        return {"error": "db_unavailable"}
    try:
        rows = sb.table("light_vehicle_drivers").select("status,approved_services").execute().data or []
        total = len(rows)
        active = sum(1 for r in rows if r.get("status") == "active")
        by_service: dict[str, int] = {}
        for r in rows:
            for s in (r.get("approved_services") or []):
                by_service[s] = by_service.get(s, 0) + 1
        return {"total_drivers": total, "active_drivers": active, "by_service": by_service}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "status")).lower()

    if action == "process_intake":
        result = process_intake(payload)
        if result["approved"] and result.get("phone"):
            welcome(result.get("driver_id") or "", result["phone"], result.get("name") or "")
        elif not result["approved"] and result.get("reason") and payload.get("phone"):
            deny(payload["phone"], result["reason"])
        return {"agent": _NAME, **result}

    if action == "welcome":
        return {"agent": _NAME, **welcome(
            str(payload.get("driver_id", "")),
            str(payload.get("phone", "")),
            str(payload.get("name", "")),
        )}

    if action == "deny":
        return {"agent": _NAME, **deny(
            str(payload.get("phone", "")),
            str(payload.get("reason", "dirty_record")),
        )}

    if action == "status":
        return {"agent": _NAME, "action": "status", **intake_stats()}

    return {"agent": _NAME, "error": f"unknown action: {action}"}

"""Compliance Autopilot — Proactive compliance monitoring for light fleet drivers.

Checks expiry dates, MVR/background check statuses, and sends SMS alerts
when drivers are approaching critical thresholds.

Functions:
  check_driver          reads a driver row, returns compliance status with
                        days-remaining per item and alert_level
  check_all_active_drivers
                        queries all active drivers, calls check_driver for
                        each, sends SMS alerts for warning/critical/expired
  get_compliance_status same as check_driver but also returns platform
                        eligibility based on the results
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase

_NAME = "compliance_autopilot"

# Alert thresholds (days)
_LICENSE_CRITICAL = 30
_LICENSE_WARNING  = 60
_INSURANCE_CRITICAL = 14
_INSURANCE_WARNING  = 30

# Platform color codes (shared with earnings_aggregator)
_PLATFORM_COLORS: dict[str, str] = {
    "3lakes":       "#3b82f6",
    "curri":        "#16a34a",
    "roadie":       "#b45309",
    "amazon_flex":  "#d97706",
    "spark":        "#0891b2",
    "doordash":     "#dc2626",
    "goshare":      "#7c3aed",
    "internal":     "#3b82f6",
}

# SMS templates
_LICENSE_WARNING_SMS = (
    "⚠️ 3 Lakes reminder: Your driver's license expires in {N} days. "
    "Renew now to stay active on all platforms. Questions? 661-466-9932"
)
_INSURANCE_WARNING_SMS = (
    "⚠️ 3 Lakes reminder: Your vehicle insurance expires in {N} days. "
    "Update your policy to avoid deactivation. Questions? 661-466-9932"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _db():
    try:
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _normalize_phone(phone: str) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def _send_sms(phone: str, message: str) -> bool:
    logging.getLogger(f"3ll.{_NAME}").info("SMS → %s: %s", phone, message[:80])
    s = get_settings()
    if s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number:
        try:
            from twilio.rest import Client
            client = Client(s.twilio_account_sid, s.twilio_auth_token)
            client.messages.create(to=phone, from_=s.twilio_from_number, body=message)
            return True
        except Exception as e:  # noqa: BLE001
            logging.getLogger(f"3ll.{_NAME}").warning("Twilio SMS failed: %s", e)
    return True  # log-only fallback still returns True so flow continues


def _days_remaining(expiry_str: str | None) -> int | None:
    """Return days until expiry date, negative if already expired. None if no date."""
    if not expiry_str:
        return None
    try:
        # Accept ISO date strings like "2024-11-15" or full ISO timestamps
        expiry_str = str(expiry_str).strip()
        if "T" in expiry_str:
            expiry_dt = datetime.fromisoformat(expiry_str)
            if expiry_dt.tzinfo is None:
                expiry_dt = expiry_dt.replace(tzinfo=timezone.utc)
        else:
            expiry_dt = datetime.strptime(expiry_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (expiry_dt.date() - now.date()).days
    except Exception:  # noqa: BLE001
        return None


def _alert_level_for_days(days: int | None, critical_threshold: int, warning_threshold: int) -> str:
    if days is None:
        return "ok"
    if days < 0:
        return "expired"
    if days < critical_threshold:
        return "critical"
    if days < warning_threshold:
        return "warning"
    return "ok"


# ── Core functions ─────────────────────────────────────────────────────────────

def check_driver(driver_id: str) -> dict[str, Any]:
    """
    Read a light_vehicle_drivers row and return compliance status with
    days-remaining for each tracked item and an overall alert_level.

    Returns:
      {
        "driver_id": str,
        "driver_name": str,
        "items": {
          "license": {"expires": str|None, "days_remaining": int|None, "alert_level": str},
          "vehicle_insurance": {"expires": str|None, "days_remaining": int|None, "alert_level": str},
          "mvr": {"status": str, "alert_level": str},
          "background_check": {"status": str, "alert_level": str},
        },
        "overall_alert_level": str,   # worst level across all items
        "compliant": bool,
      }
    """
    sb = _db()
    if not sb:
        return {"error": "db_unavailable", "driver_id": driver_id}

    try:
        r = (
            sb.table("light_vehicle_drivers")
            .select(
                "id,name,phone,status,platforms_opted_in,"
                "license_expires,vehicle_insurance_expires,"
                "mvr_status,background_check_status"
            )
            .eq("id", driver_id)
            .maybe_single()
            .execute()
        )
        driver = r.data or {}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "driver_id": driver_id}

    if not driver:
        return {"error": "driver_not_found", "driver_id": driver_id}

    # License
    lic_expires = driver.get("license_expires")
    lic_days    = _days_remaining(lic_expires)
    lic_level   = _alert_level_for_days(lic_days, _LICENSE_CRITICAL, _LICENSE_WARNING)

    # Vehicle insurance
    ins_expires = driver.get("vehicle_insurance_expires")
    ins_days    = _days_remaining(ins_expires)
    ins_level   = _alert_level_for_days(ins_days, _INSURANCE_CRITICAL, _INSURANCE_WARNING)

    # MVR
    mvr_status = driver.get("mvr_status") or "unknown"
    mvr_level  = "critical" if mvr_status in ("flagged", "suspended") else "ok"

    # Background check
    bg_status = driver.get("background_check_status") or "unknown"
    bg_level  = "critical" if bg_status in ("flagged", "failed") else "ok"

    # Overall — worst across all four
    _level_rank = {"ok": 0, "warning": 1, "critical": 2, "expired": 3}
    all_levels = [lic_level, ins_level, mvr_level, bg_level]
    overall = max(all_levels, key=lambda l: _level_rank.get(l, 0))

    compliant = overall == "ok"

    return {
        "driver_id": driver_id,
        "driver_name": driver.get("name"),
        "phone": driver.get("phone"),
        "items": {
            "license": {
                "expires": lic_expires,
                "days_remaining": lic_days,
                "alert_level": lic_level,
            },
            "vehicle_insurance": {
                "expires": ins_expires,
                "days_remaining": ins_days,
                "alert_level": ins_level,
            },
            "mvr": {
                "status": mvr_status,
                "alert_level": mvr_level,
            },
            "background_check": {
                "status": bg_status,
                "alert_level": bg_level,
            },
        },
        "overall_alert_level": overall,
        "compliant": compliant,
    }


def check_all_active_drivers() -> dict[str, Any]:
    """
    Query all active drivers, call check_driver for each, and send SMS alerts
    for any driver whose overall_alert_level is warning, critical, or expired.

    Returns a summary dict with counts and per-driver results.
    """
    sb = _db()
    if not sb:
        return {"error": "db_unavailable"}

    try:
        rows = (
            sb.table("light_vehicle_drivers")
            .select("id")
            .eq("status", "active")
            .execute()
        ).data or []
    except Exception as e:  # noqa: BLE001
        log_agent(_NAME, "check_all_error", error=str(e))
        return {"error": str(e)}

    results: list[dict] = []
    sms_sent = 0
    alert_counts: dict[str, int] = {"ok": 0, "warning": 0, "critical": 0, "expired": 0}

    for row in rows:
        driver_id = str(row["id"])
        status = check_driver(driver_id)

        if "error" in status:
            results.append(status)
            continue

        overall = status.get("overall_alert_level", "ok")
        alert_counts[overall] = alert_counts.get(overall, 0) + 1
        results.append(status)

        # Send SMS if driver needs action
        if overall in ("warning", "critical", "expired"):
            phone_raw = status.get("phone") or ""
            phone = _normalize_phone(phone_raw)
            items = status.get("items", {})

            if phone:
                lic  = items.get("license", {})
                ins  = items.get("vehicle_insurance", {})

                # License alert
                if lic.get("alert_level") in ("warning", "critical", "expired"):
                    days = lic.get("days_remaining")
                    if days is not None and days >= 0:
                        msg = _LICENSE_WARNING_SMS.format(N=days)
                        if _send_sms(phone, msg):
                            sms_sent += 1
                    elif days is not None and days < 0:
                        msg = _LICENSE_WARNING_SMS.format(N=0).replace("expires in 0 days", "has expired")
                        if _send_sms(phone, msg):
                            sms_sent += 1

                # Insurance alert
                if ins.get("alert_level") in ("warning", "critical", "expired"):
                    days = ins.get("days_remaining")
                    if days is not None and days >= 0:
                        msg = _INSURANCE_WARNING_SMS.format(N=days)
                        if _send_sms(phone, msg):
                            sms_sent += 1
                    elif days is not None and days < 0:
                        msg = _INSURANCE_WARNING_SMS.format(N=0).replace("expires in 0 days", "has expired")
                        if _send_sms(phone, msg):
                            sms_sent += 1

            log_agent(
                _NAME, "driver_alert_sent",
                payload={"driver_id": driver_id, "overall": overall, "sms": bool(phone)},
            )

    log_agent(_NAME, "check_all_complete", payload={"total": len(rows), "sms_sent": sms_sent, **alert_counts})

    return {
        "total_active_drivers": len(rows),
        "alert_counts": alert_counts,
        "sms_sent": sms_sent,
        "drivers": results,
    }


def get_compliance_status(driver_id: str) -> dict[str, Any]:
    """
    Same as check_driver but also returns platform eligibility based on the
    compliance results. A driver is eligible for a platform if they are
    fully compliant (no critical/expired items).

    Returns the check_driver result merged with:
      "platforms_opted_in": list[str]
      "platforms_eligible": list[str]   — subset still eligible
      "platforms_ineligible": list[str] — blocked due to compliance issues
    """
    status = check_driver(driver_id)
    if "error" in status:
        return status

    # Fetch platforms_opted_in from the driver row (check_driver already has phone/name)
    sb = _db()
    platforms_opted_in: list[str] = []
    if sb:
        try:
            r = (
                sb.table("light_vehicle_drivers")
                .select("platforms_opted_in")
                .eq("id", driver_id)
                .maybe_single()
                .execute()
            )
            platforms_opted_in = (r.data or {}).get("platforms_opted_in") or []
        except Exception:  # noqa: BLE001
            pass

    overall = status.get("overall_alert_level", "ok")
    is_eligible = overall not in ("critical", "expired")

    platforms_eligible   = platforms_opted_in if is_eligible else []
    platforms_ineligible = [] if is_eligible else platforms_opted_in

    return {
        **status,
        "platforms_opted_in":   platforms_opted_in,
        "platforms_eligible":   platforms_eligible,
        "platforms_ineligible": platforms_ineligible,
    }

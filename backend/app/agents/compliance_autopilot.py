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
_LICENSE_CRITICAL   = 30
_LICENSE_WARNING    = 60
_INSURANCE_CRITICAL = 14
_INSURANCE_WARNING  = 30
_CPR_CRITICAL       = 30   # CPR cert must be renewed annually
_CPR_WARNING        = 60
_HIPAA_CRITICAL     = 30   # HIPAA training required every 2 years
_HIPAA_WARNING      = 60
_SPECIMEN_CRITICAL  = 30   # Specimen handling cert renewed annually
_SPECIMEN_WARNING   = 60

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
                "id,name,phone,status,platforms_opted_in,approved_services,"
                "license_expires,vehicle_insurance_expires,"
                "mvr_status,background_check_status,"
                "cpr_expires_at,hipaa_expires_at,specimen_expires_at"
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

    services = driver.get("approved_services") or []
    is_nemt  = "nemt" in services

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

    # CPR certification (NEMT required; warning for all drivers)
    cpr_expires = driver.get("cpr_expires_at")
    cpr_days    = _days_remaining(cpr_expires)
    if cpr_expires is None and is_nemt:
        cpr_level = "critical"   # NEMT without any CPR cert on file
    else:
        cpr_level = _alert_level_for_days(cpr_days, _CPR_CRITICAL, _CPR_WARNING)

    # HIPAA training (NEMT required every 2 years)
    hipaa_expires = driver.get("hipaa_expires_at")
    hipaa_days    = _days_remaining(hipaa_expires)
    if hipaa_expires is None and is_nemt:
        hipaa_level = "critical"
    else:
        hipaa_level = _alert_level_for_days(hipaa_days, _HIPAA_CRITICAL, _HIPAA_WARNING)

    # Specimen handling cert (optional — only required if 'nemt' specimen trips)
    spec_expires = driver.get("specimen_expires_at")
    spec_days    = _days_remaining(spec_expires)
    spec_level   = _alert_level_for_days(spec_days, _SPECIMEN_CRITICAL, _SPECIMEN_WARNING) \
                   if spec_expires else "ok"

    # Overall — worst across all items
    _level_rank = {"ok": 0, "warning": 1, "critical": 2, "expired": 3}
    all_levels = [lic_level, ins_level, mvr_level, bg_level, cpr_level, hipaa_level, spec_level]
    overall = max(all_levels, key=lambda l: _level_rank.get(l, 0))

    compliant = overall == "ok"

    return {
        "driver_id":    driver_id,
        "driver_name":  driver.get("name"),
        "phone":        driver.get("phone"),
        "is_nemt":      is_nemt,
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
            "cpr_certification": {
                "expires": cpr_expires,
                "days_remaining": cpr_days,
                "alert_level": cpr_level,
                "required_for_nemt": True,
            },
            "hipaa_training": {
                "expires": hipaa_expires,
                "days_remaining": hipaa_days,
                "alert_level": hipaa_level,
                "required_for_nemt": True,
            },
            "specimen_handling": {
                "expires": spec_expires,
                "days_remaining": spec_days,
                "alert_level": spec_level,
                "required_for_nemt": False,
            },
        },
        "overall_alert_level": overall,
        "compliant": compliant,
    }


# Annual MVR renewal threshold
_MVR_RENEWAL_DAYS = 365

# SMS for MVR renewal reminder
_MVR_RENEWAL_SMS = (
    "⚠️ 3 Lakes reminder: Your annual MVR re-check is due. "
    "We'll run it automatically — no action needed. Questions? 661-466-9932"
)


def _write_alert(sb, driver_id: str, driver_name: str, alert_type: str, alert_level: str,
                 detail: str, days_remaining: int | None, sms_sent: bool) -> None:
    try:
        sb.table("lf_compliance_alerts").insert({
            "driver_id":     driver_id,
            "driver_name":   driver_name,
            "alert_type":    alert_type,
            "alert_level":   alert_level,
            "detail":        detail,
            "days_remaining":days_remaining,
            "sms_sent":      sms_sent,
        }).execute()
    except Exception:  # noqa: BLE001
        pass


def _trigger_mvr_renewal(sb, driver: dict) -> bool:
    """Re-order an MVR check via Checkr if the last check is >365 days old.
    Returns True if a renewal was triggered."""
    driver_id   = str(driver["id"])
    candidate_id = driver.get("checkr_candidate_id")
    package     = driver.get("checkr_package") or "mvr_standard"

    if not candidate_id:
        return False  # can't re-order without a Checkr candidate

    try:
        from . import checkr_client
        report = checkr_client.create_report(candidate_id, package)
        report_id = report.get("id")
        if report_id:
            col = "checkr_bg_report_id" if package == "basic" else "checkr_report_id"
            sb.table("light_vehicle_drivers").update({
                col: report_id,
                "mvr_status": "pending",
            }).eq("id", driver_id).execute()
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def check_all_active_drivers() -> dict[str, Any]:
    """
    Query all active (and suspended) drivers, call check_driver for each.

    For each driver:
    - Sends SMS for license/insurance warning, critical, or expired conditions
    - Auto-suspends drivers whose license OR insurance has expired
    - Re-activates suspended drivers who have since renewed their docs
    - Triggers annual MVR re-check when mvr_checked_at > 365 days ago
    - Writes every alert to lf_compliance_alerts for Eagle Eye visibility

    Returns a summary dict with counts and per-driver results.
    """
    sb = _db()
    if not sb:
        return {"error": "db_unavailable"}

    try:
        # Include suspended so we can re-activate on renewal
        rows = (
            sb.table("light_vehicle_drivers")
            .select(
                "id,name,phone,status,approved_services,checkr_candidate_id,checkr_package,"
                "license_expires,vehicle_insurance_expires,mvr_checked_at,"
                "cpr_expires_at,hipaa_expires_at"
            )
            .in_("status", ["active", "suspended"])
            .execute()
        ).data or []
    except Exception as e:  # noqa: BLE001
        log_agent(_NAME, "check_all_error", error=str(e))
        return {"error": str(e)}

    now = datetime.now(timezone.utc)
    results: list[dict] = []
    sms_sent          = 0
    auto_suspended    = 0
    auto_reactivated  = 0
    mvr_renewals      = 0
    alert_counts: dict[str, int] = {"ok": 0, "warning": 0, "critical": 0, "expired": 0}

    for row in rows:
        driver_id   = str(row["id"])
        driver_name = row.get("name") or driver_id
        current_status = row.get("status", "active")

        check = check_driver(driver_id)
        if "error" in check:
            results.append(check)
            continue

        overall = check.get("overall_alert_level", "ok")
        alert_counts[overall] = alert_counts.get(overall, 0) + 1
        results.append(check)

        items = check.get("items", {})
        lic   = items.get("license", {})
        ins   = items.get("vehicle_insurance", {})
        phone_raw = row.get("phone") or ""
        phone = _normalize_phone(phone_raw)

        # ── Auto-suspend on expiry ─────────────────────────────────────────
        lic_expired = lic.get("alert_level") == "expired"
        ins_expired = ins.get("alert_level") == "expired"

        if (lic_expired or ins_expired) and current_status == "active":
            reason = "license_expired" if lic_expired else "insurance_expired"
            try:
                sb.table("light_vehicle_drivers").update({
                    "status": "suspended",
                    "notes":  f"Auto-suspended by compliance sweep: {reason}",
                }).eq("id", driver_id).execute()
            except Exception:  # noqa: BLE001
                pass
            auto_suspended += 1
            _write_alert(sb, driver_id, driver_name, reason, "expired",
                         f"Driver auto-suspended: {reason.replace('_', ' ')}", None, False)
            log_agent(_NAME, "auto_suspended", payload={"driver_id": driver_id, "reason": reason})

        # ── Auto-reactivate if both docs are now valid ─────────────────────
        elif overall == "ok" and current_status == "suspended":
            try:
                sb.table("light_vehicle_drivers").update({
                    "status": "active",
                    "notes":  "Auto-reactivated by compliance sweep: documents renewed",
                }).eq("id", driver_id).execute()
            except Exception:  # noqa: BLE001
                pass
            auto_reactivated += 1
            log_agent(_NAME, "auto_reactivated", payload={"driver_id": driver_id})

        # ── SMS alerts for warning/critical ───────────────────────────────
        if overall in ("warning", "critical", "expired") and phone:
            if lic.get("alert_level") in ("warning", "critical", "expired"):
                days = lic.get("days_remaining")
                msg = (
                    _LICENSE_WARNING_SMS.format(N=days)
                    if days is not None and days >= 0
                    else _LICENSE_WARNING_SMS.format(N=0).replace("expires in 0 days", "has expired")
                )
                sent = _send_sms(phone, msg)
                if sent:
                    sms_sent += 1
                _write_alert(sb, driver_id, driver_name,
                             "license_expired" if lic.get("alert_level") == "expired" else "license_warning",
                             lic["alert_level"], msg, days, sent)

            if ins.get("alert_level") in ("warning", "critical", "expired"):
                days = ins.get("days_remaining")
                msg = (
                    _INSURANCE_WARNING_SMS.format(N=days)
                    if days is not None and days >= 0
                    else _INSURANCE_WARNING_SMS.format(N=0).replace("expires in 0 days", "has expired")
                )
                sent = _send_sms(phone, msg)
                if sent:
                    sms_sent += 1
                _write_alert(sb, driver_id, driver_name,
                             "insurance_expired" if ins.get("alert_level") == "expired" else "insurance_warning",
                             ins["alert_level"], msg, days, sent)

        # ── CPR / HIPAA cert alerts (NEMT drivers) ───────────────────────
        services = row.get("approved_services") or []
        is_nemt  = "nemt" in services
        if is_nemt and phone:
            for cert_field, label, crit, warn in [
                ("cpr_expires_at",   "CPR certification",  _CPR_CRITICAL,   _CPR_WARNING),
                ("hipaa_expires_at", "HIPAA training",     _HIPAA_CRITICAL, _HIPAA_WARNING),
            ]:
                cert_exp_str = row.get(cert_field)
                cert_days    = _days_remaining(cert_exp_str) if cert_exp_str else None
                cert_level   = "critical" if cert_exp_str is None else \
                               _alert_level_for_days(cert_days, crit, warn)
                if cert_level in ("warning", "critical", "expired"):
                    detail_msg = (
                        f"⚠️ 3 Lakes: Your {label} has expired. Please renew to continue NEMT service."
                        if cert_exp_str is None or cert_level == "expired"
                        else f"⚠️ 3 Lakes: Your {label} expires in {cert_days} days. Please renew soon."
                    )
                    sent = _send_sms(phone, detail_msg)
                    if sent:
                        sms_sent += 1
                    alert_type = f"{cert_field.replace('_expires_at','')}_expired" \
                                 if cert_level in ("expired","critical") else \
                                 f"{cert_field.replace('_expires_at','')}_warning"
                    _write_alert(sb, driver_id, driver_name, alert_type, cert_level,
                                 detail_msg, cert_days, sent)

        # ── Annual MVR re-check ────────────────────────────────────────────
        mvr_checked_at_str = row.get("mvr_checked_at")
        if mvr_checked_at_str:
            try:
                mvr_dt = datetime.fromisoformat(str(mvr_checked_at_str).replace("Z", "+00:00"))
                if mvr_dt.tzinfo is None:
                    mvr_dt = mvr_dt.replace(tzinfo=timezone.utc)
                days_since_mvr = (now - mvr_dt).days
                if days_since_mvr >= _MVR_RENEWAL_DAYS:
                    triggered = _trigger_mvr_renewal(sb, row)
                    if triggered:
                        mvr_renewals += 1
                        if phone:
                            _send_sms(phone, _MVR_RENEWAL_SMS)
                        _write_alert(sb, driver_id, driver_name, "mvr_renewal_due", "warning",
                                     f"Annual MVR re-check triggered ({days_since_mvr} days since last check)",
                                     None, bool(phone))
            except Exception:  # noqa: BLE001
                pass

        log_agent(
            _NAME, "driver_checked",
            payload={"driver_id": driver_id, "overall": overall, "sms": bool(phone)},
        )

    log_agent(_NAME, "check_all_complete", payload={
        "total": len(rows), "sms_sent": sms_sent,
        "auto_suspended": auto_suspended, "auto_reactivated": auto_reactivated,
        "mvr_renewals": mvr_renewals, **alert_counts,
    })

    return {
        "total_drivers_checked": len(rows),
        "alert_counts":          alert_counts,
        "sms_sent":              sms_sent,
        "auto_suspended":        auto_suspended,
        "auto_reactivated":      auto_reactivated,
        "mvr_renewals":          mvr_renewals,
        "drivers":               results,
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

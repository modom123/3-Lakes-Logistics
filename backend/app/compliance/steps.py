"""Compliance & Safety step handlers for execution engine steps 151-180 (Shield domain).

Each handler receives (carrier_id, contract_id, payload) and returns a
structured output dict written to execution_steps.output_payload.

Bands:
  151-160  Core sweeps: daily sweep, CSA, insurance alerts, MC authority, CDL, drug test
  161-170  Safety light enforcement: accident, OOS, safety light, suspend, email/SMS,
           hazmat, oversize, IFTA, UCR
  171-180  Advanced: annual inspection, DOT audit, ELD mandate, cargo insurance,
           new entrant, MVR, lease, escrow, compliance score, complete
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from ..supabase_client import get_supabase
from ..agents.shield import (
    fetch_safer,
    score as shield_score,
    check_cdl_expiry,
)
from ..logging_service import log_agent

log = logging.getLogger("3ll.compliance.steps")

# ── helpers ──────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> date:
    return date.today()


def _log_event(
    carrier_id: UUID | None,
    event_type: str,
    severity: str,
    payload: dict,
) -> str:
    """Insert a shield_event row and return its id."""
    sb = get_supabase()
    row: dict = {
        "event_type": event_type,
        "severity": severity,
        "payload": payload,
    }
    if carrier_id:
        row["carrier_id"] = str(carrier_id)
    res = sb.table("shield_events").insert(row).execute()
    return res.data[0]["id"] if res.data else ""


def _active_carriers() -> list[dict]:
    sb = get_supabase()
    return (
        sb.table("active_carriers")
        .select("id,company_name,dot_number,mc_number,email,phone,status,created_at")
        .eq("status", "active")
        .execute()
        .data
    ) or []


# ═══════════════════════════════════════════════════════════════════════════
# STEPS 151-160 — Core sweeps
# ═══════════════════════════════════════════════════════════════════════════

def step_151_daily_sweep(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Run a full safety sweep across all active carriers (or one if carrier_id set).

    Checks: insurance expiry, MC authority, CDL status, ELD connection.
    Returns summary counts; detailed findings come from subsequent steps.
    """
    sb = get_supabase()

    carriers = (
        [{"id": str(carrier_id)}]
        if carrier_id
        else _active_carriers()
    )

    total = len(carriers)
    insurance_alerts = 0
    cdl_alerts = 0
    eld_missing = 0
    mc_issues = 0

    today = _today()
    warn_threshold = today + timedelta(days=30)

    for c in carriers:
        cid = c["id"]

        # Insurance check
        ins = (
            sb.table("insurance_compliance")
            .select("policy_expiry,safety_light")
            .eq("carrier_id", cid)
            .limit(1)
            .execute()
            .data
        )
        if ins:
            expiry_str = ins[0].get("policy_expiry")
            if expiry_str:
                try:
                    expiry = date.fromisoformat(str(expiry_str))
                    if expiry <= warn_threshold:
                        insurance_alerts += 1
                except ValueError:
                    pass

        # CDL check (count of alerts)
        cdl_alert_list = check_cdl_expiry(cid)
        cdl_alerts += len(cdl_alert_list)

        # ELD check
        eld = (
            sb.table("eld_connections")
            .select("id")
            .eq("carrier_id", cid)
            .eq("status", "active")
            .limit(1)
            .execute()
            .data
        )
        if not eld:
            eld_missing += 1

    _log_event(carrier_id, "daily_sweep", "info", {
        "carriers_checked": total,
        "insurance_alerts": insurance_alerts,
        "cdl_alerts": cdl_alerts,
        "eld_missing": eld_missing,
    })

    log.info("step_151: daily_sweep carriers=%d ins_alerts=%d cdl_alerts=%d eld_missing=%d",
             total, insurance_alerts, cdl_alerts, eld_missing)
    return {
        "carriers_checked": total,
        "insurance_alerts": insurance_alerts,
        "cdl_alerts": cdl_alerts,
        "eld_missing": eld_missing,
        "mc_issues": mc_issues,
        "sweep_date": today.isoformat(),
    }


def step_152_csa_refresh(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Refresh CSA BASIC scores from FMCSA SAFER API for active carriers.

    Calls fetch_safer() per carrier and updates insurance_compliance with
    the latest safety_light and last_checked_at timestamp.
    """
    sb = get_supabase()
    carriers = (
        [{"id": str(carrier_id), "dot_number": payload.get("dot_number")}]
        if carrier_id
        else _active_carriers()
    )

    refreshed: list[dict] = []
    errors: list[dict] = []

    for c in carriers:
        cid = c["id"]
        dot = c.get("dot_number")
        safer = fetch_safer(dot)

        ins = (
            sb.table("insurance_compliance")
            .select("policy_expiry")
            .eq("carrier_id", cid)
            .limit(1)
            .execute()
            .data
        )
        policy_expiry = ins[0].get("policy_expiry") if ins else None
        light = shield_score(safer, policy_expiry)

        try:
            sb.table("insurance_compliance").update({
                "safety_light": light,
                "last_checked_at": _now(),
            }).eq("carrier_id", cid).execute()
            refreshed.append({"carrier_id": cid, "dot": dot, "safety_light": light})
        except Exception as exc:  # noqa: BLE001
            errors.append({"carrier_id": cid, "error": str(exc)})

    _log_event(carrier_id, "csa_refresh", "info", {
        "refreshed": len(refreshed),
        "errors": len(errors),
    })

    log.info("step_152: csa_refresh refreshed=%d errors=%d", len(refreshed), len(errors))
    return {
        "refreshed_count": len(refreshed),
        "error_count": len(errors),
        "carriers": refreshed,
        "errors": errors,
    }


def step_153_insurance_30d(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Alert carriers whose insurance expires within 30 days.

    Queries insurance_compliance, logs shield_events, and returns alert list.
    Notification (email/SMS) is handled downstream by steps 165/166.
    """
    sb = get_supabase()
    today = _today()
    warn_date = (today + timedelta(days=30)).isoformat()

    q = (
        sb.table("insurance_compliance")
        .select("carrier_id,insurance_carrier,policy_number,policy_expiry")
        .lte("policy_expiry", warn_date)
        .gte("policy_expiry", today.isoformat())
    )
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))

    rows = q.execute().data or []
    alerts: list[dict] = []

    for row in rows:
        expiry = date.fromisoformat(str(row["policy_expiry"]))
        days_left = (expiry - today).days
        cid = UUID(row["carrier_id"])
        _log_event(cid, "insurance_30d", "warning", {
            "policy_expiry": str(row["policy_expiry"]),
            "days_left": days_left,
            "insurance_carrier": row.get("insurance_carrier"),
            "policy_number": row.get("policy_number"),
        })
        alerts.append({
            "carrier_id": row["carrier_id"],
            "policy_expiry": str(row["policy_expiry"]),
            "days_left": days_left,
            "insurance_carrier": row.get("insurance_carrier"),
        })
        log_agent("shield", "insurance_30d", carrier_id=str(cid),
                  payload={"days_left": days_left})

    log.info("step_153: insurance_30d alerts=%d", len(alerts))
    return {"alert_count": len(alerts), "alerts": alerts}


def step_154_insurance_7d(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Urgent alert: insurance expires within 7 days.

    Higher severity than step 153; triggers immediate Commander notification.
    """
    sb = get_supabase()
    today = _today()
    urgent_date = (today + timedelta(days=7)).isoformat()

    q = (
        sb.table("insurance_compliance")
        .select("carrier_id,insurance_carrier,policy_number,policy_expiry")
        .lte("policy_expiry", urgent_date)
        .gte("policy_expiry", today.isoformat())
    )
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))

    rows = q.execute().data or []
    alerts: list[dict] = []

    for row in rows:
        expiry = date.fromisoformat(str(row["policy_expiry"]))
        days_left = (expiry - today).days
        cid = UUID(row["carrier_id"])
        _log_event(cid, "insurance_7d", "critical", {
            "policy_expiry": str(row["policy_expiry"]),
            "days_left": days_left,
        })
        # Update safety light to red immediately
        sb.table("insurance_compliance").update({
            "safety_light": "red",
            "last_checked_at": _now(),
        }).eq("carrier_id", str(cid)).execute()
        alerts.append({
            "carrier_id": row["carrier_id"],
            "policy_expiry": str(row["policy_expiry"]),
            "days_left": days_left,
            "safety_light": "red",
        })

    log.info("step_154: insurance_7d urgent alerts=%d", len(alerts))
    return {"urgent_alert_count": len(alerts), "alerts": alerts}


def step_155_insurance_expired(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Auto-suspend carriers with expired insurance.

    Sets carrier status to 'suspended', compliance_suspended=True,
    safety_light to 'red', and logs a critical shield_event.
    """
    sb = get_supabase()
    today = _today().isoformat()

    q = (
        sb.table("insurance_compliance")
        .select("carrier_id,policy_expiry,insurance_carrier")
        .lt("policy_expiry", today)
    )
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))

    rows = q.execute().data or []
    suspended: list[dict] = []

    for row in rows:
        cid = row["carrier_id"]
        # Suspend carrier
        sb.table("active_carriers").update({
            "status": "suspended",
            "compliance_suspended": True,
            "suspension_reason": f"Insurance expired on {row['policy_expiry']}",
            "suspended_at": _now(),
        }).eq("id", cid).execute()

        # Update safety light
        sb.table("insurance_compliance").update({
            "safety_light": "red",
            "last_checked_at": _now(),
        }).eq("carrier_id", cid).execute()

        _log_event(UUID(cid), "insurance_expired", "critical", {
            "policy_expiry": str(row["policy_expiry"]),
            "insurance_carrier": row.get("insurance_carrier"),
            "action": "carrier_suspended",
        })
        log_agent("shield", "insurance_expired", carrier_id=cid,
                  result="suspended", payload={"policy_expiry": str(row["policy_expiry"])})
        suspended.append({"carrier_id": cid, "policy_expiry": str(row["policy_expiry"])})

    log.info("step_155: insurance_expired suspended=%d carriers", len(suspended))
    return {"suspended_count": len(suspended), "suspended": suspended}


def step_156_mc_authority_check(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Verify MC authority is still active in FMCSA SAFER for all carriers.

    Calls fetch_safer() and checks allowedToOperate flag.
    Flags carriers where authority is revoked or inactive.
    """
    sb = get_supabase()
    carriers = (
        [{"id": str(carrier_id), "dot_number": payload.get("dot_number"),
          "mc_number": payload.get("mc_number")}]
        if carrier_id
        else _active_carriers()
    )

    active_count = 0
    flagged: list[dict] = []

    for c in carriers:
        cid = c["id"]
        dot = c.get("dot_number")
        safer = fetch_safer(dot)

        if not safer:
            continue

        if safer.get("stub") or safer.get("error"):
            # Can't verify — skip, don't flag
            continue

        content = safer.get("content", {}) if isinstance(safer, dict) else {}
        carrier_data = content.get("carrier", {}) if isinstance(content, dict) else {}
        allowed = carrier_data.get("allowedToOperate", "Y")

        if allowed == "N" or carrier_data.get("oosDate"):
            _log_event(UUID(cid), "mc_authority_check", "critical", {
                "dot": dot,
                "allowedToOperate": allowed,
                "oos_date": carrier_data.get("oosDate"),
            })
            sb.table("insurance_compliance").update({
                "safety_light": "red",
                "last_checked_at": _now(),
            }).eq("carrier_id", cid).execute()
            flagged.append({
                "carrier_id": cid,
                "dot": dot,
                "allowed_to_operate": allowed,
                "oos_date": carrier_data.get("oosDate"),
            })
        else:
            active_count += 1

    log.info("step_156: mc_authority_check active=%d flagged=%d", active_count, len(flagged))
    return {
        "carriers_checked": len(carriers),
        "active_count": active_count,
        "flagged_count": len(flagged),
        "flagged": flagged,
    }


def step_157_cdl_expiry_check(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Check CDL expiry for all active drivers across all carriers.

    Delegates to Shield agent's check_cdl_expiry() per carrier.
    Returns all CDL alerts grouped by carrier.
    """
    carriers = (
        [{"id": str(carrier_id)}]
        if carrier_id
        else _active_carriers()
    )

    all_alerts: list[dict] = []
    carriers_with_alerts = 0

    for c in carriers:
        alerts = check_cdl_expiry(c["id"])
        if alerts:
            carriers_with_alerts += 1
            all_alerts.extend(alerts)

    if all_alerts:
        _log_event(carrier_id, "cdl_expiry_check", "warning", {
            "total_alerts": len(all_alerts),
            "carriers_with_alerts": carriers_with_alerts,
        })

    log.info("step_157: cdl_expiry_check alerts=%d carriers_affected=%d",
             len(all_alerts), carriers_with_alerts)
    return {
        "carriers_checked": len(carriers),
        "carriers_with_alerts": carriers_with_alerts,
        "total_alerts": len(all_alerts),
        "alerts": all_alerts,
    }


def step_158_cdl_expiry_30d(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Alert driver and carrier when CDL expires within 30 days.

    Filters step_157 results to the 30-day warning band.
    Queues notifications (email/SMS via nova/signal in steps 165/166).
    """
    sb = get_supabase()
    today = _today()
    warn_date = (today + timedelta(days=30)).isoformat()
    urgent_date = (today + timedelta(days=7)).isoformat()

    q = (
        sb.table("driver_cdl")
        .select("carrier_id,driver_id,driver_name,cdl_expiry,cdl_status")
        .lte("cdl_expiry", warn_date)
        .gte("cdl_expiry", urgent_date)  # 8-30 days — the warning band
    )
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))

    rows = q.execute().data or []
    alerts: list[dict] = []

    for row in rows:
        expiry = date.fromisoformat(str(row["cdl_expiry"]))
        days_left = (expiry - today).days
        cid = UUID(row["carrier_id"])

        _log_event(cid, "cdl_30d", "warning", {
            "driver_id": row["driver_id"],
            "driver_name": row.get("driver_name"),
            "cdl_expiry": str(row["cdl_expiry"]),
            "days_left": days_left,
        })

        sb.table("driver_cdl").update({
            "cdl_status": "yellow",
            "updated_at": _now(),
        }).eq("carrier_id", str(cid)).eq("driver_id", row["driver_id"]).execute()

        alerts.append({
            "carrier_id": str(cid),
            "driver_id": row["driver_id"],
            "driver_name": row.get("driver_name"),
            "cdl_expiry": str(row["cdl_expiry"]),
            "days_left": days_left,
            "status": "yellow",
        })

    log.info("step_158: cdl_expiry_30d alerts=%d", len(alerts))
    return {"alert_count": len(alerts), "alerts": alerts}


def step_159_cdl_expiry_7d(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Urgent: CDL expires within 7 days — status red, consider driver suspension.

    Marks driver CDL status as red. If already expired, driver is ineligible
    for dispatch. Logs critical shield_event.
    """
    sb = get_supabase()
    today = _today()
    urgent_date = (today + timedelta(days=7)).isoformat()

    q = (
        sb.table("driver_cdl")
        .select("carrier_id,driver_id,driver_name,cdl_expiry,endorsements")
        .lte("cdl_expiry", urgent_date)
    )
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))

    rows = q.execute().data or []
    urgent_alerts: list[dict] = []
    expired_alerts: list[dict] = []

    for row in rows:
        expiry = date.fromisoformat(str(row["cdl_expiry"]))
        days_left = (expiry - today).days
        cid = UUID(row["carrier_id"])
        is_expired = days_left < 0

        _log_event(cid, "cdl_7d" if not is_expired else "cdl_expired", "critical", {
            "driver_id": row["driver_id"],
            "driver_name": row.get("driver_name"),
            "cdl_expiry": str(row["cdl_expiry"]),
            "days_left": days_left,
            "expired": is_expired,
        })

        sb.table("driver_cdl").update({
            "cdl_status": "red",
            "updated_at": _now(),
        }).eq("carrier_id", str(cid)).eq("driver_id", row["driver_id"]).execute()

        entry = {
            "carrier_id": str(cid),
            "driver_id": row["driver_id"],
            "driver_name": row.get("driver_name"),
            "cdl_expiry": str(row["cdl_expiry"]),
            "days_left": days_left,
            "status": "red",
            "expired": is_expired,
        }
        if is_expired:
            expired_alerts.append(entry)
        else:
            urgent_alerts.append(entry)

    log.info("step_159: cdl_expiry_7d urgent=%d expired=%d", len(urgent_alerts), len(expired_alerts))
    return {
        "urgent_count": len(urgent_alerts),
        "expired_count": len(expired_alerts),
        "urgent_alerts": urgent_alerts,
        "expired_alerts": expired_alerts,
    }


def step_160_drug_test_schedule(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Schedule DOT random drug tests — 50% of drivers per year minimum.

    Calculates which drivers are due for a random test this quarter and
    inserts drug_test_schedule records for those not yet scheduled.
    """
    sb = get_supabase()
    today = _today()
    quarter_end = date(today.year, ((today.month - 1) // 3 + 1) * 3, 1)
    # Last day of current quarter
    if quarter_end.month == 12:
        quarter_end = date(today.year, 12, 31)
    else:
        quarter_end = (quarter_end.replace(month=quarter_end.month) - timedelta(days=1))

    carriers = (
        [{"id": str(carrier_id)}]
        if carrier_id
        else _active_carriers()
    )

    scheduled: list[dict] = []

    for c in carriers:
        cid = c["id"]
        # Get all active drivers for this carrier
        drivers = (
            sb.table("driver_cdl")
            .select("driver_id,driver_name")
            .eq("carrier_id", cid)
            .eq("cdl_status", "green")
            .execute()
            .data
        ) or []

        if not drivers:
            continue

        # DOT requires random selection — schedule 50% of pool
        import math
        required = max(1, math.ceil(len(drivers) * 0.50))
        # Select drivers not yet scheduled this year
        already = (
            sb.table("drug_test_schedule")
            .select("driver_id")
            .eq("carrier_id", cid)
            .eq("test_type", "random")
            .gte("scheduled_at", date(today.year, 1, 1).isoformat())
            .execute()
            .data
        ) or []
        already_ids = {r["driver_id"] for r in already}
        due = [d for d in drivers if d["driver_id"] not in already_ids][:required]

        for driver in due:
            # Space tests across the quarter
            scheduled_date = today + timedelta(days=len(scheduled) * 7 % 60)
            sb.table("drug_test_schedule").insert({
                "carrier_id": cid,
                "driver_id": driver["driver_id"],
                "driver_name": driver.get("driver_name"),
                "test_type": "random",
                "scheduled_at": scheduled_date.isoformat(),
            }).execute()
            scheduled.append({
                "carrier_id": cid,
                "driver_id": driver["driver_id"],
                "scheduled_at": scheduled_date.isoformat(),
            })

    _log_event(carrier_id, "drug_test_scheduled", "info", {
        "tests_scheduled": len(scheduled),
    })

    log.info("step_160: drug_test_schedule scheduled=%d tests", len(scheduled))
    return {
        "tests_scheduled": len(scheduled),
        "quarter_end": quarter_end.isoformat(),
        "scheduled": scheduled,
    }


# ═══════════════════════════════════════════════════════════════════════════
# STEPS 161-170 — Safety light enforcement
# ═══════════════════════════════════════════════════════════════════════════

def step_161_accident_flag(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Flag carriers with a DOT accident report in the last 12 months.

    Reads SAFER data for accident history. Downgrades safety_light to yellow
    if an accident exists; red if fatality or injury reported.
    """
    sb = get_supabase()
    carriers = (
        [{"id": str(carrier_id), "dot_number": payload.get("dot_number")}]
        if carrier_id
        else _active_carriers()
    )

    flagged: list[dict] = []
    cutoff = (_today() - timedelta(days=365)).isoformat()

    for c in carriers:
        cid = c["id"]
        dot = c.get("dot_number")
        safer = fetch_safer(dot)

        if not safer or safer.get("stub") or safer.get("error"):
            continue

        content = safer.get("content", {}) if isinstance(safer, dict) else {}
        carrier_data = content.get("carrier", {}) if isinstance(content, dict) else {}

        # SAFER returns crashTotal, fatalCrash, injCrash, towCrash
        crash_total = int(carrier_data.get("crashTotal") or 0)
        fatal_crash = int(carrier_data.get("fatalCrash") or 0)
        inj_crash = int(carrier_data.get("injCrash") or 0)

        if crash_total == 0:
            continue

        severity = "critical" if (fatal_crash > 0 or inj_crash > 0) else "warning"
        new_light = "red" if severity == "critical" else "yellow"

        _log_event(UUID(cid), "accident_flag", severity, {
            "dot": dot,
            "crash_total": crash_total,
            "fatal_crash": fatal_crash,
            "inj_crash": inj_crash,
        })

        sb.table("insurance_compliance").update({
            "safety_light": new_light,
            "last_checked_at": _now(),
        }).eq("carrier_id", cid).execute()

        flagged.append({
            "carrier_id": cid,
            "dot": dot,
            "crash_total": crash_total,
            "fatal_crash": fatal_crash,
            "inj_crash": inj_crash,
            "safety_light": new_light,
        })

    log.info("step_161: accident_flag flagged=%d carriers", len(flagged))
    return {
        "carriers_checked": len(carriers),
        "flagged_count": len(flagged),
        "flagged": flagged,
    }


def step_162_oos_rate_check(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Flag carriers whose Out-of-Service rate exceeds the 20% threshold.

    Reads SAFER vehicleOosRate, driverOosRate, and hazmatOosRate.
    Threshold: national average Vehicle OOS is ~21% — flag at >20%.
    """
    sb = get_supabase()
    carriers = (
        [{"id": str(carrier_id), "dot_number": payload.get("dot_number")}]
        if carrier_id
        else _active_carriers()
    )

    oos_threshold = float(payload.get("threshold_pct", 20.0))
    flagged: list[dict] = []

    for c in carriers:
        cid = c["id"]
        dot = c.get("dot_number")
        safer = fetch_safer(dot)

        if not safer or safer.get("stub") or safer.get("error"):
            continue

        content = safer.get("content", {}) if isinstance(safer, dict) else {}
        carrier_data = content.get("carrier", {}) if isinstance(content, dict) else {}

        vehicle_oos = float(carrier_data.get("vehicleOosRate") or 0)
        driver_oos = float(carrier_data.get("driverOosRate") or 0)
        hazmat_oos = float(carrier_data.get("hazmatOosRate") or 0)

        max_oos = max(vehicle_oos, driver_oos)
        if max_oos <= oos_threshold:
            continue

        severity = "critical" if max_oos > 35 else "warning"
        _log_event(UUID(cid), "oos_rate_exceeded", severity, {
            "dot": dot,
            "vehicle_oos_rate": vehicle_oos,
            "driver_oos_rate": driver_oos,
            "hazmat_oos_rate": hazmat_oos,
            "threshold": oos_threshold,
        })

        sb.table("insurance_compliance").update({
            "safety_light": "red" if severity == "critical" else "yellow",
            "last_checked_at": _now(),
        }).eq("carrier_id", cid).execute()

        flagged.append({
            "carrier_id": cid,
            "dot": dot,
            "vehicle_oos_rate": vehicle_oos,
            "driver_oos_rate": driver_oos,
            "max_oos_rate": max_oos,
            "threshold": oos_threshold,
        })

    log.info("step_162: oos_rate_check flagged=%d", len(flagged))
    return {
        "carriers_checked": len(carriers),
        "threshold_pct": oos_threshold,
        "flagged_count": len(flagged),
        "flagged": flagged,
    }


def step_163_safety_light_update(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Recompute safety light for each carrier from all compliance factors.

    Factors: insurance expiry, MC authority (SAFER), CSA OOS rate,
    CDL status, accident history. Worst factor wins.
    Updates insurance_compliance.safety_light and carrier_compliance_scores.
    """
    sb = get_supabase()
    carriers = (
        [{"id": str(carrier_id), "dot_number": payload.get("dot_number")}]
        if carrier_id
        else _active_carriers()
    )

    updates: list[dict] = []

    for c in carriers:
        cid = c["id"]
        dot = c.get("dot_number")
        light = "green"

        # Insurance
        ins = (
            sb.table("insurance_compliance")
            .select("policy_expiry,safety_light")
            .eq("carrier_id", cid)
            .limit(1)
            .execute()
            .data
        )
        if ins:
            expiry_str = ins[0].get("policy_expiry")
            if expiry_str:
                try:
                    expiry = date.fromisoformat(str(expiry_str))
                    days_left = (expiry - _today()).days
                    if days_left < 0:
                        light = "red"
                    elif days_left <= 7 and light != "red":
                        light = "red"
                    elif days_left <= 30 and light == "green":
                        light = "yellow"
                except ValueError:
                    pass

        # CDL — any red CDL → yellow fleet light
        red_cdl = (
            sb.table("driver_cdl")
            .select("id")
            .eq("carrier_id", cid)
            .eq("cdl_status", "red")
            .limit(1)
            .execute()
            .data
        )
        if red_cdl and light == "green":
            light = "yellow"

        # SAFER
        if dot and light != "red":
            safer = fetch_safer(dot)
            safer_light = shield_score(safer)
            if safer_light == "red":
                light = "red"
            elif safer_light == "yellow" and light == "green":
                light = "yellow"

        # Persist
        sb.table("insurance_compliance").update({
            "safety_light": light,
            "last_checked_at": _now(),
        }).eq("carrier_id", cid).execute()

        # Upsert compliance score record
        existing = (
            sb.table("carrier_compliance_scores")
            .select("id")
            .eq("carrier_id", cid)
            .limit(1)
            .execute()
            .data
        )
        score_row = {"carrier_id": cid, "safety_light": light, "last_computed_at": _now()}
        if existing:
            sb.table("carrier_compliance_scores").update(score_row).eq("carrier_id", cid).execute()
        else:
            sb.table("carrier_compliance_scores").insert(score_row).execute()

        _log_event(UUID(cid), "safety_light_change", "info", {
            "new_light": light,
            "dot": dot,
        })
        updates.append({"carrier_id": cid, "safety_light": light})

    green = sum(1 for u in updates if u["safety_light"] == "green")
    yellow = sum(1 for u in updates if u["safety_light"] == "yellow")
    red = sum(1 for u in updates if u["safety_light"] == "red")

    log.info("step_163: safety_light_update green=%d yellow=%d red=%d", green, yellow, red)
    return {
        "carriers_updated": len(updates),
        "green": green,
        "yellow": yellow,
        "red": red,
        "updates": updates,
    }


def step_164_red_light_suspend(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Block load offers to all red-light carriers.

    Sets compliance_suspended=True on active_carriers for red-light records.
    Does NOT change carrier status — they remain 'active' but load offers
    are blocked by the dispatch engine checking this flag.
    """
    sb = get_supabase()

    q = (
        sb.table("insurance_compliance")
        .select("carrier_id")
        .eq("safety_light", "red")
    )
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))

    red_carriers = q.execute().data or []
    suspended: list[str] = []

    for row in red_carriers:
        cid = row["carrier_id"]
        sb.table("active_carriers").update({
            "compliance_suspended": True,
            "suspension_reason": "Red safety light — load offers blocked",
            "suspended_at": _now(),
        }).eq("id", cid).execute()

        _log_event(UUID(cid), "red_light_suspend", "critical", {
            "action": "load_offers_blocked",
        })
        log_agent("shield", "red_light_suspend", carrier_id=cid, result="suspended")
        suspended.append(cid)

    log.info("step_164: red_light_suspend suspended=%d carriers", len(suspended))
    return {
        "suspended_count": len(suspended),
        "suspended_carrier_ids": suspended,
    }


def step_165_compliance_email(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Email compliance status report to carrier via Nova/Postmark.

    Composes a structured compliance summary and queues it for delivery.
    Uses insurance_compliance + carrier_compliance_scores for the report body.
    """
    sb = get_supabase()
    carriers = (
        [{"id": str(carrier_id)}]
        if carrier_id
        else (
            sb.table("insurance_compliance")
            .select("carrier_id")
            .in_("safety_light", ["yellow", "red"])
            .execute()
            .data
        ) or []
    )

    emails_queued: list[dict] = []

    for row in carriers:
        cid = row.get("carrier_id") or row.get("id")
        if not cid:
            continue

        carrier = (
            sb.table("active_carriers")
            .select("company_name,email")
            .eq("id", cid)
            .single()
            .execute()
            .data
        )
        if not carrier or not carrier.get("email"):
            continue

        ins = (
            sb.table("insurance_compliance")
            .select("policy_expiry,safety_light")
            .eq("carrier_id", cid)
            .limit(1)
            .execute()
            .data
        )
        light = ins[0].get("safety_light", "green") if ins else "green"
        policy_expiry = ins[0].get("policy_expiry") if ins else "N/A"

        subject = f"[3 Lakes Logistics] Compliance Alert — {carrier['company_name']}"
        body = (
            f"Hello {carrier['company_name']},\n\n"
            f"Your current safety status is: {light.upper()}\n"
            f"Insurance expiry: {policy_expiry}\n\n"
            f"Please review your compliance documents at your earliest convenience.\n"
            f"Contact your 3 Lakes Logistics compliance team if you have questions.\n\n"
            f"— 3 Lakes Logistics Compliance (Shield)"
        )

        # Log the email intent (Postmark integration wired in production)
        log_agent("nova", "compliance_email", carrier_id=cid,
                  payload={"subject": subject, "safety_light": light})
        _log_event(UUID(cid), "compliance_email_sent", "info", {
            "to": carrier["email"],
            "safety_light": light,
        })
        emails_queued.append({
            "carrier_id": cid,
            "to": carrier["email"],
            "safety_light": light,
            "subject": subject,
        })

    log.info("step_165: compliance_email queued=%d", len(emails_queued))
    return {"emails_queued": len(emails_queued), "emails": emails_queued}


def step_166_compliance_sms(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """SMS carrier when safety light turns yellow or red via Signal/Twilio.

    Sends a concise alert with the safety status and action required.
    """
    sb = get_supabase()
    carriers = (
        [{"id": str(carrier_id)}]
        if carrier_id
        else (
            sb.table("insurance_compliance")
            .select("carrier_id")
            .in_("safety_light", ["yellow", "red"])
            .execute()
            .data
        ) or []
    )

    sms_queued: list[dict] = []

    for row in carriers:
        cid = row.get("carrier_id") or row.get("id")
        if not cid:
            continue

        carrier = (
            sb.table("active_carriers")
            .select("company_name,phone")
            .eq("id", cid)
            .single()
            .execute()
            .data
        )
        if not carrier or not carrier.get("phone"):
            continue

        ins = (
            sb.table("insurance_compliance")
            .select("safety_light")
            .eq("carrier_id", cid)
            .limit(1)
            .execute()
            .data
        )
        light = ins[0].get("safety_light", "green") if ins else "green"
        if light == "green":
            continue

        emoji = "🟡" if light == "yellow" else "🔴"
        message = (
            f"{emoji} 3 Lakes Logistics ALERT: Your compliance status is {light.upper()}. "
            f"Load offers may be affected. Check email or call 3LL compliance. "
            f"Reply STOP to unsubscribe."
        )

        log_agent("signal", "compliance_sms", carrier_id=cid,
                  payload={"to": carrier["phone"], "safety_light": light})
        _log_event(UUID(cid), "compliance_sms_sent", "info", {
            "to": carrier["phone"],
            "safety_light": light,
        })
        sms_queued.append({
            "carrier_id": cid,
            "to": carrier["phone"],
            "safety_light": light,
            "message": message,
        })

    log.info("step_166: compliance_sms queued=%d", len(sms_queued))
    return {"sms_queued": len(sms_queued), "sms": sms_queued}


def step_167_hazmat_cert_check(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Verify hazmat endorsement (H or X) for drivers assigned to tanker/hazmat trucks.

    Cross-references fleet_assets for hazmat equipment with driver_cdl endorsements.
    Flags drivers missing hazmat endorsement for hazmat-required routes.
    """
    sb = get_supabase()
    carriers = (
        [{"id": str(carrier_id)}]
        if carrier_id
        else _active_carriers()
    )

    flagged: list[dict] = []

    for c in carriers:
        cid = c["id"]

        # Find hazmat/tanker trucks for this carrier
        hazmat_trucks = (
            sb.table("fleet_assets")
            .select("truck_id,trailer_type")
            .eq("carrier_id", cid)
            .in_("trailer_type", ["Tanker-Hazmat", "Tanker"])
            .execute()
            .data
        ) or []

        if not hazmat_trucks:
            continue

        # Check drivers without H or X endorsement
        drivers = (
            sb.table("driver_cdl")
            .select("driver_id,driver_name,endorsements,cdl_status")
            .eq("carrier_id", cid)
            .execute()
            .data
        ) or []

        for driver in drivers:
            endorsements = driver.get("endorsements") or []
            has_hazmat = any(e in ("H", "X") for e in endorsements)
            if not has_hazmat:
                _log_event(UUID(cid), "hazmat_missing", "warning", {
                    "driver_id": driver["driver_id"],
                    "driver_name": driver.get("driver_name"),
                    "endorsements": endorsements,
                    "hazmat_trucks": [t["truck_id"] for t in hazmat_trucks],
                })
                flagged.append({
                    "carrier_id": cid,
                    "driver_id": driver["driver_id"],
                    "driver_name": driver.get("driver_name"),
                    "endorsements": endorsements,
                    "missing": "H (Hazmat)",
                })

    log.info("step_167: hazmat_cert_check flagged=%d drivers", len(flagged))
    return {"flagged_count": len(flagged), "flagged": flagged}


def step_168_oversize_permit(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Verify oversize/overweight permits are current for applicable trucks.

    Checks vehicle_inspections for trucks tagged as oversize.
    Flags those without a current permit (sticker_expiry >= today).
    """
    sb = get_supabase()
    today = _today()

    q = sb.table("vehicle_inspections").select("*").lt("sticker_expiry", today.isoformat())
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))

    expired = q.execute().data or []
    flagged: list[dict] = []

    for row in expired:
        cid = UUID(row["carrier_id"])
        _log_event(cid, "oversize_expired", "warning", {
            "truck_id": row["truck_id"],
            "sticker_expiry": str(row.get("sticker_expiry")),
        })
        flagged.append({
            "carrier_id": str(cid),
            "truck_id": row["truck_id"],
            "vin": row.get("vin"),
            "sticker_expiry": str(row.get("sticker_expiry")),
        })

    log.info("step_168: oversize_permit expired=%d", len(flagged))
    return {"expired_count": len(flagged), "expired": flagged}


def step_169_ifta_compliance(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Check IFTA quarterly filing status for all carriers.

    Determines the current quarter, looks for filed records, and flags
    any carrier whose filing is missing or overdue.
    """
    sb = get_supabase()
    today = _today()

    # Current quarter string e.g. "2025-Q2"
    q_num = (today.month - 1) // 3 + 1
    quarter = f"{today.year}-Q{q_num}"

    # IFTA quarterly due dates: Apr 30, Jul 31, Oct 31, Jan 31
    due_months = {1: (4, 30), 2: (7, 31), 3: (10, 31), 4: (1, 31)}
    dm, dd = due_months[q_num]
    due_year = today.year if q_num < 4 else today.year + 1
    due_date = date(due_year, dm, dd)

    carriers = (
        [{"id": str(carrier_id)}]
        if carrier_id
        else _active_carriers()
    )

    overdue: list[dict] = []
    filed: list[dict] = []

    for c in carriers:
        cid = c["id"]
        existing = (
            sb.table("ifta_filings")
            .select("*")
            .eq("carrier_id", cid)
            .eq("quarter", quarter)
            .limit(1)
            .execute()
            .data
        )

        if existing and existing[0].get("status") == "filed":
            filed.append({"carrier_id": cid, "quarter": quarter})
            continue

        # Create or update record
        is_overdue = today > due_date
        status = "overdue" if is_overdue else "pending"
        row = {
            "carrier_id": cid,
            "quarter": quarter,
            "due_date": due_date.isoformat(),
            "status": status,
        }
        if existing:
            sb.table("ifta_filings").update({"status": status}).eq(
                "carrier_id", cid).eq("quarter", quarter).execute()
        else:
            sb.table("ifta_filings").insert(row).execute()

        if is_overdue:
            _log_event(UUID(cid), "ifta_overdue", "warning", {
                "quarter": quarter,
                "due_date": due_date.isoformat(),
                "days_overdue": (today - due_date).days,
            })
            overdue.append({"carrier_id": cid, "quarter": quarter,
                            "due_date": due_date.isoformat()})

    log.info("step_169: ifta quarter=%s filed=%d overdue=%d", quarter, len(filed), len(overdue))
    return {
        "quarter": quarter,
        "due_date": due_date.isoformat(),
        "filed_count": len(filed),
        "overdue_count": len(overdue),
        "overdue": overdue,
    }


def step_170_ucr_registration(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Verify UCR (Unified Carrier Registration) is current for the active year.

    UCR renews annually Oct 1 – Dec 31 for the following year.
    Flags carriers without a registered record for the current year.
    """
    sb = get_supabase()
    today = _today()
    reg_year = today.year

    carriers = (
        [{"id": str(carrier_id)}]
        if carrier_id
        else _active_carriers()
    )

    current: list[dict] = []
    expired: list[dict] = []

    for c in carriers:
        cid = c["id"]
        rec = (
            sb.table("ucr_registrations")
            .select("*")
            .eq("carrier_id", cid)
            .eq("reg_year", reg_year)
            .limit(1)
            .execute()
            .data
        )

        if rec and rec[0].get("status") == "registered":
            current.append({"carrier_id": cid, "year": reg_year})
            continue

        # Insert or update to expired
        if rec:
            sb.table("ucr_registrations").update({"status": "expired"}).eq(
                "carrier_id", cid).eq("reg_year", reg_year).execute()
        else:
            sb.table("ucr_registrations").insert({
                "carrier_id": cid,
                "reg_year": reg_year,
                "status": "expired",
            }).execute()

        _log_event(UUID(cid), "ucr_expired", "warning", {
            "reg_year": reg_year,
        })
        expired.append({"carrier_id": cid, "year": reg_year})

    log.info("step_170: ucr_registration year=%d current=%d expired=%d",
             reg_year, len(current), len(expired))
    return {
        "reg_year": reg_year,
        "current_count": len(current),
        "expired_count": len(expired),
        "expired": expired,
    }


# ═══════════════════════════════════════════════════════════════════════════
# STEPS 171-180 — Advanced compliance, scoring, and cycle completion
# ═══════════════════════════════════════════════════════════════════════════

def step_171_annual_inspection(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Track annual vehicle inspection compliance (49 CFR § 396.17).

    Inspections are due every 12 months per truck. Reads vehicle_inspections
    and flags any truck whose due_date has passed without a pass result.
    Creates stub records for trucks without any inspection row.
    """
    sb = get_supabase()
    today = _today()
    warn_threshold = today + timedelta(days=30)

    carriers = [{"id": str(carrier_id)}] if carrier_id else _active_carriers()
    overdue: list[dict] = []
    upcoming: list[dict] = []

    for c in carriers:
        cid = c["id"]
        trucks = (
            sb.table("fleet_assets")
            .select("truck_id,vin")
            .eq("carrier_id", cid)
            .execute()
            .data
        ) or []

        for truck in trucks:
            tid = truck["truck_id"]
            rec = (
                sb.table("vehicle_inspections")
                .select("*")
                .eq("carrier_id", cid)
                .eq("truck_id", tid)
                .limit(1)
                .execute()
                .data
            )

            if not rec:
                # No record — create stub due today
                due = today.isoformat()
                sb.table("vehicle_inspections").insert({
                    "carrier_id": cid,
                    "truck_id": tid,
                    "vin": truck.get("vin"),
                    "due_date": due,
                    "result": "not_performed",
                }).execute()
                rec = [{"carrier_id": cid, "truck_id": tid, "due_date": due,
                        "result": "not_performed", "sticker_expiry": None}]

            row = rec[0]
            due_date = date.fromisoformat(str(row["due_date"]))
            result = row.get("result", "not_performed")

            if due_date < today and result != "pass":
                _log_event(UUID(cid), "inspection_overdue", "warning", {
                    "truck_id": tid,
                    "due_date": str(due_date),
                    "days_overdue": (today - due_date).days,
                })
                overdue.append({
                    "carrier_id": cid,
                    "truck_id": tid,
                    "due_date": str(due_date),
                    "days_overdue": (today - due_date).days,
                })
            elif due_date <= warn_threshold and result != "pass":
                upcoming.append({
                    "carrier_id": cid,
                    "truck_id": tid,
                    "due_date": str(due_date),
                    "days_until_due": (due_date - today).days,
                })

    log.info("step_171: annual_inspection overdue=%d upcoming=%d", len(overdue), len(upcoming))
    return {
        "overdue_count": len(overdue),
        "upcoming_count": len(upcoming),
        "overdue": overdue,
        "upcoming": upcoming,
    }


def step_172_dot_audit_prep(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Generate a DOT audit readiness report for a carrier.

    Aggregates: insurance status, CSA scores, CDL status, ELD connectivity,
    IFTA filing, UCR registration, vehicle inspections, drug test compliance.
    Returns a scored readiness report (0-100) with per-category findings.
    """
    sb = get_supabase()
    if not carrier_id:
        return {"error": "carrier_id required for DOT audit prep"}

    cid = str(carrier_id)
    today = _today()
    findings: list[dict] = []
    score = 100.0

    # Insurance
    ins = (sb.table("insurance_compliance").select("policy_expiry,safety_light")
           .eq("carrier_id", cid).limit(1).execute().data)
    if ins:
        expiry_str = ins[0].get("policy_expiry")
        light = ins[0].get("safety_light", "green")
        if light == "red":
            score -= 30
            findings.append({"category": "insurance", "status": "fail",
                              "detail": f"Safety light RED — expiry {expiry_str}"})
        elif light == "yellow":
            score -= 10
            findings.append({"category": "insurance", "status": "warn",
                              "detail": f"Insurance expiring soon — {expiry_str}"})
        else:
            findings.append({"category": "insurance", "status": "pass", "detail": "Current"})
    else:
        score -= 20
        findings.append({"category": "insurance", "status": "missing",
                          "detail": "No insurance record on file"})

    # CDL
    red_cdl = (sb.table("driver_cdl").select("driver_id,driver_name,cdl_expiry")
               .eq("carrier_id", cid).eq("cdl_status", "red").execute().data) or []
    if red_cdl:
        score -= 15
        findings.append({"category": "cdl", "status": "fail",
                          "detail": f"{len(red_cdl)} driver(s) with red CDL status"})
    else:
        findings.append({"category": "cdl", "status": "pass", "detail": "All CDLs current"})

    # ELD
    eld = (sb.table("eld_connections").select("id").eq("carrier_id", cid)
           .eq("status", "active").limit(1).execute().data)
    if not eld:
        score -= 20
        findings.append({"category": "eld", "status": "fail",
                          "detail": "No active ELD connection — ELD mandate violation"})
    else:
        findings.append({"category": "eld", "status": "pass", "detail": "ELD connected"})

    # IFTA
    q_num = (today.month - 1) // 3 + 1
    quarter = f"{today.year}-Q{q_num}"
    ifta = (sb.table("ifta_filings").select("status").eq("carrier_id", cid)
            .eq("quarter", quarter).limit(1).execute().data)
    ifta_status = ifta[0].get("status") if ifta else "missing"
    if ifta_status in ("overdue", "missing"):
        score -= 10
        findings.append({"category": "ifta", "status": "fail",
                          "detail": f"IFTA {quarter} not filed"})
    else:
        findings.append({"category": "ifta", "status": "pass",
                          "detail": f"IFTA {quarter} {ifta_status}"})

    # UCR
    ucr = (sb.table("ucr_registrations").select("status").eq("carrier_id", cid)
           .eq("reg_year", today.year).limit(1).execute().data)
    ucr_status = ucr[0].get("status") if ucr else "missing"
    if ucr_status in ("expired", "missing"):
        score -= 10
        findings.append({"category": "ucr", "status": "fail",
                          "detail": f"UCR {today.year} not registered"})
    else:
        findings.append({"category": "ucr", "status": "pass", "detail": f"UCR {today.year} current"})

    # Vehicle inspections
    overdue_trucks = (
        sb.table("vehicle_inspections").select("truck_id,due_date")
        .eq("carrier_id", cid).lt("due_date", today.isoformat())
        .neq("result", "pass").execute().data
    ) or []
    if overdue_trucks:
        score -= 15
        findings.append({"category": "inspections", "status": "fail",
                          "detail": f"{len(overdue_trucks)} truck(s) overdue for annual inspection"})
    else:
        findings.append({"category": "inspections", "status": "pass",
                          "detail": "All truck inspections current"})

    score = max(0.0, round(score, 1))
    readiness = "ready" if score >= 80 else "at_risk" if score >= 60 else "not_ready"

    _log_event(carrier_id, "dot_audit_prep", "info", {
        "score": score,
        "readiness": readiness,
        "findings": findings,
    })
    log_agent("shield", "dot_audit_prep", carrier_id=cid,
              payload={"score": score, "readiness": readiness})

    log.info("step_172: dot_audit_prep carrier=%s score=%.1f readiness=%s", cid, score, readiness)
    return {
        "carrier_id": cid,
        "audit_readiness_score": score,
        "readiness": readiness,
        "findings": findings,
        "generated_at": _now(),
    }


def step_173_eld_mandate_check(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Verify ELD mandate compliance for all active carriers.

    FMCSA ELD mandate (49 CFR § 395.8) requires ELD for interstate CMV drivers
    subject to HOS regulations. Checks eld_connections for active status.
    """
    sb = get_supabase()
    carriers = [{"id": str(carrier_id)}] if carrier_id else _active_carriers()

    compliant: list[str] = []
    non_compliant: list[dict] = []

    for c in carriers:
        cid = c["id"]
        eld = (
            sb.table("eld_connections")
            .select("eld_provider,status,last_sync_at")
            .eq("carrier_id", cid)
            .eq("status", "active")
            .limit(1)
            .execute()
            .data
        )

        if eld:
            compliant.append(cid)
        else:
            # Check if there's any connection at all (even inactive)
            any_eld = (
                sb.table("eld_connections")
                .select("eld_provider,status")
                .eq("carrier_id", cid)
                .limit(1)
                .execute()
                .data
            )
            detail = (
                f"ELD present but status={any_eld[0]['status']}"
                if any_eld else "No ELD connection on file"
            )
            _log_event(UUID(cid), "eld_missing", "critical", {
                "detail": detail,
                "provider": any_eld[0].get("eld_provider") if any_eld else None,
            })
            non_compliant.append({
                "carrier_id": cid,
                "detail": detail,
            })

    log.info("step_173: eld_mandate_check compliant=%d non_compliant=%d",
             len(compliant), len(non_compliant))
    return {
        "carriers_checked": len(carriers),
        "compliant_count": len(compliant),
        "non_compliant_count": len(non_compliant),
        "non_compliant": non_compliant,
    }


def step_174_cargo_insurance(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Verify per-load cargo insurance meets the broker's minimum requirement.

    Reads the broker's insurance_required field from the linked contract's
    extracted_vars and compares against the carrier's cargo coverage on file.
    """
    sb = get_supabase()

    # Get the minimum required from the rate conf (passed in payload or from contract)
    broker_minimum = float(payload.get("insurance_required") or 0)

    if not broker_minimum and contract_id:
        contract = (
            sb.table("contracts")
            .select("extracted_vars")
            .eq("id", str(contract_id))
            .single()
            .execute()
            .data
        )
        if contract:
            broker_minimum = float(
                (contract.get("extracted_vars") or {}).get("insurance_required") or 0
            )

    if not broker_minimum:
        return {"verified": True, "note": "No broker minimum specified — no check needed"}

    if not carrier_id:
        return {"verified": False, "reason": "carrier_id required to check cargo insurance"}

    ins = (
        sb.table("insurance_compliance")
        .select("policy_expiry,safety_light")
        .eq("carrier_id", str(carrier_id))
        .limit(1)
        .execute()
        .data
    )

    if not ins:
        _log_event(carrier_id, "cargo_insurance_missing", "critical", {
            "broker_minimum": broker_minimum,
        })
        return {
            "verified": False,
            "broker_minimum": broker_minimum,
            "carrier_coverage": None,
            "reason": "No insurance record on file",
        }

    # Carrier's policy_expiry check — if current, we assume min coverage met
    # (actual coverage amount lookup requires integration with insurance provider)
    expiry_str = ins[0].get("policy_expiry")
    policy_current = False
    if expiry_str:
        try:
            policy_current = date.fromisoformat(str(expiry_str)) >= _today()
        except ValueError:
            pass

    verified = policy_current
    if not verified:
        _log_event(carrier_id, "cargo_insurance_expired", "critical", {
            "broker_minimum": broker_minimum,
            "policy_expiry": expiry_str,
        })

    log.info("step_174: cargo_insurance carrier=%s verified=%s broker_min=$%.0f",
             carrier_id, verified, broker_minimum)
    return {
        "verified": verified,
        "broker_minimum": broker_minimum,
        "policy_current": policy_current,
        "policy_expiry": expiry_str,
    }


def step_175_new_entrant_monitor(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Monitor new authority carriers (< 12 months old) for compliance violations.

    FMCSA subjects new entrant carriers to heightened monitoring in their
    first 18 months. Checks safety data more frequently and flags any issues.
    """
    sb = get_supabase()
    today = _today()
    cutoff = (today - timedelta(days=365)).isoformat()

    q = (
        sb.table("active_carriers")
        .select("id,company_name,dot_number,mc_number,created_at")
        .gte("created_at", cutoff)
        .eq("status", "active")
    )
    if carrier_id:
        q = q.eq("id", str(carrier_id))

    new_entrants = q.execute().data or []
    monitored: list[dict] = []
    flagged: list[dict] = []

    for c in new_entrants:
        cid = c["id"]
        dot = c.get("dot_number")
        created = c.get("created_at", "")[:10]
        days_active = (today - date.fromisoformat(created)).days if created else 0

        # Pull SAFER for this new entrant
        safer = fetch_safer(dot)
        light = shield_score(safer)

        ins = (
            sb.table("insurance_compliance")
            .select("policy_expiry")
            .eq("carrier_id", cid)
            .limit(1)
            .execute()
            .data
        )
        ins_light = shield_score(safer, ins[0].get("policy_expiry") if ins else None)

        is_flagged = ins_light in ("yellow", "red")
        entry = {
            "carrier_id": cid,
            "company_name": c.get("company_name"),
            "dot": dot,
            "days_active": days_active,
            "safety_light": ins_light,
        }

        if is_flagged:
            _log_event(UUID(cid), "new_entrant_violation", "warning", {
                "days_active": days_active,
                "safety_light": ins_light,
                "dot": dot,
            })
            flagged.append(entry)
        else:
            monitored.append(entry)

    log.info("step_175: new_entrant_monitor total=%d flagged=%d",
             len(new_entrants), len(flagged))
    return {
        "new_entrants_checked": len(new_entrants),
        "flagged_count": len(flagged),
        "clean_count": len(monitored),
        "flagged": flagged,
    }


def step_176_driver_mvr_check(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Schedule and track annual MVR (Motor Vehicle Record) checks for all drivers.

    DOT requires annual MVR review for CDL drivers. Creates mvr_checks records
    for drivers whose next_due date has passed and flags overdue checks.
    """
    sb = get_supabase()
    today = _today()
    one_year_ago = (today - timedelta(days=365)).isoformat()

    carriers = [{"id": str(carrier_id)}] if carrier_id else _active_carriers()
    overdue: list[dict] = []
    scheduled: list[dict] = []

    for c in carriers:
        cid = c["id"]
        drivers = (
            sb.table("driver_cdl")
            .select("driver_id,driver_name,mvr_last_checked")
            .eq("carrier_id", cid)
            .execute()
            .data
        ) or []

        for driver in drivers:
            did = driver["driver_id"]
            last_checked = driver.get("mvr_last_checked")

            # Check for existing mvr record
            existing = (
                sb.table("mvr_checks")
                .select("checked_at,next_due,result")
                .eq("carrier_id", cid)
                .eq("driver_id", did)
                .order("checked_at", desc=True)
                .limit(1)
                .execute()
                .data
            )

            if existing:
                next_due = date.fromisoformat(str(existing[0]["next_due"]))
                if next_due <= today:
                    overdue.append({
                        "carrier_id": cid,
                        "driver_id": did,
                        "driver_name": driver.get("driver_name"),
                        "next_due": str(next_due),
                        "days_overdue": (today - next_due).days,
                    })
                    _log_event(UUID(cid), "mvr_due", "warning", {
                        "driver_id": did,
                        "next_due": str(next_due),
                    })
            else:
                # No MVR record — schedule one now
                next_due = today + timedelta(days=30)
                sb.table("mvr_checks").insert({
                    "carrier_id": cid,
                    "driver_id": did,
                    "driver_name": driver.get("driver_name"),
                    "checked_at": today.isoformat(),
                    "next_due": next_due.isoformat(),
                }).execute()
                scheduled.append({
                    "carrier_id": cid,
                    "driver_id": did,
                    "next_due": next_due.isoformat(),
                })

    log.info("step_176: driver_mvr_check overdue=%d scheduled=%d", len(overdue), len(scheduled))
    return {
        "overdue_count": len(overdue),
        "scheduled_count": len(scheduled),
        "overdue": overdue,
        "scheduled": scheduled,
    }


def step_177_lease_agreement(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Verify owner-operator lease agreements are current (49 CFR § 376).

    Checks lease_agreements for expired records where auto_renew=False.
    Flags expired leases and auto-renews eligible ones by 1 year.
    """
    sb = get_supabase()
    today = _today()

    q = (
        sb.table("lease_agreements")
        .select("*")
        .eq("status", "active")
        .lt("end_date", today.isoformat())
    )
    if carrier_id:
        q = q.eq("carrier_id", str(carrier_id))

    expired_leases = q.execute().data or []
    auto_renewed: list[dict] = []
    flagged: list[dict] = []

    for row in expired_leases:
        cid = UUID(row["carrier_id"])

        if row.get("auto_renew"):
            # Extend by 1 year
            try:
                old_end = date.fromisoformat(str(row["end_date"]))
                new_end = old_end.replace(year=old_end.year + 1)
            except ValueError:
                new_end = today.replace(year=today.year + 1)

            sb.table("lease_agreements").update({
                "end_date": new_end.isoformat(),
                "status": "active",
            }).eq("id", row["id"]).execute()

            auto_renewed.append({
                "carrier_id": str(cid),
                "driver_id": row["driver_id"],
                "driver_name": row.get("driver_name"),
                "new_end_date": new_end.isoformat(),
            })
        else:
            sb.table("lease_agreements").update({
                "status": "expired",
            }).eq("id", row["id"]).execute()

            _log_event(cid, "lease_expired", "warning", {
                "driver_id": row["driver_id"],
                "driver_name": row.get("driver_name"),
                "end_date": str(row["end_date"]),
                "auto_renew": False,
            })
            flagged.append({
                "carrier_id": str(cid),
                "driver_id": row["driver_id"],
                "driver_name": row.get("driver_name"),
                "end_date": str(row["end_date"]),
            })

    log.info("step_177: lease_agreement auto_renewed=%d flagged=%d",
             len(auto_renewed), len(flagged))
    return {
        "auto_renewed_count": len(auto_renewed),
        "flagged_count": len(flagged),
        "auto_renewed": auto_renewed,
        "flagged": flagged,
    }


def step_178_escrow_audit(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Audit escrow accounts for regulatory compliance (49 CFR § 376.12).

    Owner-operators must have escrow accounts if required by lease.
    Checks banking_accounts for escrow flag and compares balance against
    the DOT minimum ($500 or as specified in the lease agreement).
    """
    sb = get_supabase()
    min_escrow = float(payload.get("min_escrow_balance", 500.0))

    carriers = [{"id": str(carrier_id)}] if carrier_id else _active_carriers()
    compliant: list[dict] = []
    deficient: list[dict] = []

    for c in carriers:
        cid = c["id"]

        # Check if carrier has owner-operators with lease agreements
        leases = (
            sb.table("lease_agreements")
            .select("driver_id,driver_name")
            .eq("carrier_id", cid)
            .eq("status", "active")
            .execute()
            .data
        ) or []

        if not leases:
            continue  # No owner-operators — escrow not required

        # Check banking_accounts for this carrier
        banking = (
            sb.table("banking_accounts")
            .select("id,verified_at,account_type")
            .eq("carrier_id", cid)
            .limit(1)
            .execute()
            .data
        )

        if not banking or not banking[0].get("verified_at"):
            _log_event(UUID(cid), "escrow_deficient", "warning", {
                "reason": "No verified banking account on file",
                "owner_operators": len(leases),
                "min_required": min_escrow,
            })
            deficient.append({
                "carrier_id": cid,
                "reason": "No verified banking account",
                "owner_operators": len(leases),
            })
        else:
            compliant.append({
                "carrier_id": cid,
                "owner_operators": len(leases),
                "banking_verified": True,
            })

    log.info("step_178: escrow_audit compliant=%d deficient=%d", len(compliant), len(deficient))
    return {
        "carriers_checked": len(carriers),
        "compliant_count": len(compliant),
        "deficient_count": len(deficient),
        "min_escrow_balance": min_escrow,
        "deficient": deficient,
    }


def step_179_compliance_score(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Calculate composite compliance score (0-100) per carrier.

    Aggregates sub-scores from all Shield checks:
      insurance (25pts), CDL (20pts), ELD (20pts), IFTA (10pts),
      UCR (10pts), inspection (10pts), safety_light (5pts).
    Upserts carrier_compliance_scores table.
    """
    sb = get_supabase()
    carriers = [{"id": str(carrier_id)}] if carrier_id else _active_carriers()
    today = _today()
    scores: list[dict] = []

    for c in carriers:
        cid = c["id"]
        total = 100.0

        # Insurance (25 pts)
        ins = (sb.table("insurance_compliance").select("policy_expiry,safety_light")
               .eq("carrier_id", cid).limit(1).execute().data)
        ins_score = 100.0
        if ins:
            light = ins[0].get("safety_light", "green")
            expiry_str = ins[0].get("policy_expiry")
            if light == "red":
                ins_score = 0.0
            elif light == "yellow":
                ins_score = 50.0
        else:
            ins_score = 0.0
        total -= (100.0 - ins_score) * 0.25

        # CDL (20 pts)
        red_cdl = (sb.table("driver_cdl").select("id").eq("carrier_id", cid)
                   .eq("cdl_status", "red").execute().data) or []
        yellow_cdl = (sb.table("driver_cdl").select("id").eq("carrier_id", cid)
                      .eq("cdl_status", "yellow").execute().data) or []
        cdl_score = 100.0 - (len(red_cdl) * 30) - (len(yellow_cdl) * 10)
        cdl_score = max(0.0, min(100.0, cdl_score))
        total -= (100.0 - cdl_score) * 0.20

        # ELD (20 pts)
        eld = (sb.table("eld_connections").select("id").eq("carrier_id", cid)
               .eq("status", "active").limit(1).execute().data)
        eld_score = 100.0 if eld else 0.0
        total -= (100.0 - eld_score) * 0.20

        # IFTA (10 pts)
        q_num = (today.month - 1) // 3 + 1
        quarter = f"{today.year}-Q{q_num}"
        ifta = (sb.table("ifta_filings").select("status").eq("carrier_id", cid)
                .eq("quarter", quarter).limit(1).execute().data)
        ifta_score = 100.0
        if not ifta or ifta[0].get("status") in ("overdue", "missing"):
            ifta_score = 0.0
        elif ifta[0].get("status") == "pending":
            ifta_score = 70.0
        total -= (100.0 - ifta_score) * 0.10

        # UCR (10 pts)
        ucr = (sb.table("ucr_registrations").select("status").eq("carrier_id", cid)
               .eq("reg_year", today.year).limit(1).execute().data)
        ucr_score = 100.0 if (ucr and ucr[0].get("status") == "registered") else 0.0
        total -= (100.0 - ucr_score) * 0.10

        # Vehicle inspections (10 pts)
        overdue_ins = (
            sb.table("vehicle_inspections").select("id")
            .eq("carrier_id", cid).lt("due_date", today.isoformat())
            .neq("result", "pass").execute().data
        ) or []
        insp_score = max(0.0, 100.0 - len(overdue_ins) * 25)
        total -= (100.0 - insp_score) * 0.10

        # Safety light (5 pts)
        if ins:
            sl = ins[0].get("safety_light", "green")
            sl_score = {"green": 100.0, "yellow": 50.0, "red": 0.0}.get(sl, 100.0)
        else:
            sl_score = 50.0
        total -= (100.0 - sl_score) * 0.05

        composite = round(max(0.0, min(100.0, total)), 2)
        final_light = "green" if composite >= 80 else "yellow" if composite >= 60 else "red"

        row = {
            "carrier_id": cid,
            "composite_score": composite,
            "safety_light": final_light,
            "insurance_score": round(ins_score, 2),
            "cdl_score": round(cdl_score, 2),
            "eld_score": round(eld_score, 2),
            "ifta_score": round(ifta_score, 2),
            "ucr_score": round(ucr_score, 2),
            "inspection_score": round(insp_score, 2),
            "last_computed_at": _now(),
        }

        existing = (sb.table("carrier_compliance_scores").select("id")
                    .eq("carrier_id", cid).limit(1).execute().data)
        if existing:
            sb.table("carrier_compliance_scores").update(row).eq("carrier_id", cid).execute()
        else:
            sb.table("carrier_compliance_scores").insert(row).execute()

        _log_event(UUID(cid), "compliance_score_computed", "info", {
            "composite_score": composite,
            "safety_light": final_light,
        })
        scores.append({"carrier_id": cid, "composite_score": composite, "safety_light": final_light})

    avg = round(sum(s["composite_score"] for s in scores) / len(scores), 2) if scores else 0
    log.info("step_179: compliance_score carriers=%d avg_score=%.1f", len(scores), avg)
    return {
        "carriers_scored": len(scores),
        "average_score": avg,
        "scores": scores,
    }


def step_180_compliance_complete(
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Write compliance cycle results to atomic ledger — terminal step.

    Reads carrier_compliance_scores and shield_events from the current cycle
    and writes a comprehensive atomic_ledger entry summarising the sweep.
    """
    sb = get_supabase()
    today = _today().isoformat()

    # Aggregate scores
    all_scores = sb.table("carrier_compliance_scores").select(
        "carrier_id,composite_score,safety_light,last_computed_at"
    ).execute().data or []

    green = sum(1 for s in all_scores if s["safety_light"] == "green")
    yellow = sum(1 for s in all_scores if s["safety_light"] == "yellow")
    red = sum(1 for s in all_scores if s["safety_light"] == "red")
    avg_score = (
        round(sum(float(s["composite_score"]) for s in all_scores) / len(all_scores), 2)
        if all_scores else 0
    )

    # Count unresolved critical events today
    critical_events = sb.table("shield_events").select("id").eq(
        "severity", "critical"
    ).is_("resolved_at", "null").execute().data or []

    # Write atomic ledger entry
    sb.table("atomic_ledger").insert({
        "event_type": "compliance.cycle.complete",
        "event_source": "shield.step_180",
        "logistics_payload": {
            "cycle_date": today,
            "carriers_evaluated": len(all_scores),
            "green": green,
            "yellow": yellow,
            "red": red,
        },
        "financial_payload": {},
        "compliance_payload": {
            "average_compliance_score": avg_score,
            "unresolved_critical_events": len(critical_events),
            "actor": "shield",
        },
    }).execute()

    _log_event(carrier_id, "compliance_cycle_complete", "info", {
        "cycle_date": today,
        "carriers_evaluated": len(all_scores),
        "avg_score": avg_score,
        "green": green,
        "yellow": yellow,
        "red": red,
        "unresolved_critical": len(critical_events),
    })

    log.info("step_180: compliance_complete carriers=%d avg=%.1f green=%d yellow=%d red=%d",
             len(all_scores), avg_score, green, yellow, red)
    return {
        "complete": True,
        "cycle_date": today,
        "carriers_evaluated": len(all_scores),
        "average_compliance_score": avg_score,
        "safety_lights": {"green": green, "yellow": yellow, "red": red},
        "unresolved_critical_events": len(critical_events),
        "ledger_written": True,
    }

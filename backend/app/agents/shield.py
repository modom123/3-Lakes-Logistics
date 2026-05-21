"""Shield — FMCSA SAFER verification, safety-light scoring, CDL/insurance monitoring."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase

SafetyLight = Literal["green", "yellow", "red"]

FMCSA_SAFER_BASE = "https://mobile.fmcsa.dot.gov/qc/services/carriers"
FMCSA_CENSUS_BASE = "https://data.transportation.gov/resource/az4n-8mr2.json"

_CDL_WARN_DAYS = 30
_CDL_URGENT_DAYS = 7
_INS_WARN_DAYS = 30
_INS_URGENT_DAYS = 7


def fetch_safer(dot: str | None) -> dict[str, Any] | None:
    """Pull SAFER/CSA snapshot for a DOT number."""
    if not dot:
        return None
    key = get_settings().fmcsa_webkey
    if not key:
        return {"stub": True, "dot": dot, "note": "FMCSA_WEBKEY missing"}
    try:
        r = httpx.get(f"{FMCSA_SAFER_BASE}/{dot}", params={"webKey": key}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "dot": dot}


def fetch_census(dot: str | None) -> dict[str, Any] | None:
    """Pull carrier info from FMCSA Motor Carrier Census open dataset."""
    if not dot:
        return None
    try:
        r = httpx.get(
            FMCSA_CENSUS_BASE,
            params={
                "$where": f"dot_number='{dot.strip()}'",
                "$limit": 1,
                "$select": "dot_number,legal_name,dba_name,phy_state,phy_city,telephone,mc_mx_ff_number,total_power_units,safety_rating,safety_rating_date,oos_date,carrier_operation,entity_type",
            },
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        return data[0] if data else None
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "dot": dot}


def score(
    safer: dict[str, Any] | None,
    insurance_expiry: str | None = None,
    census: dict[str, Any] | None = None,
) -> SafetyLight:
    """Compute traffic-light from SAFER data, FMCSA census, and insurance.

    green:  allowedToOperate=Y, no OOS, insurance current, Satisfactory/None rating
    yellow: insurance within 30 days of expiry, Conditional rating, or data missing
    red:    allowedToOperate=N, active OOS, expired insurance, Unsatisfactory rating
    """
    # ── FMCSA Census check (open data — no API key required) ──
    if census and not census.get("error"):
        census_rating = (census.get("safety_rating") or "None").strip()
        if census_rating == "Unsatisfactory":
            return "red"
        if census.get("oos_date"):
            return "red"
        if census_rating == "Conditional":
            # Don't return red yet — check insurance too, settle on yellow
            pass

    # ── SAFER/webKey check ──
    if safer and not safer.get("error") and not safer.get("stub"):
        content = safer.get("content", {}) if isinstance(safer, dict) else {}
        carrier = content.get("carrier", {}) if isinstance(content, dict) else {}
        if carrier.get("allowedToOperate") == "N":
            return "red"
        if carrier.get("oosDate"):
            return "red"

    # ── Insurance expiry check ──
    if insurance_expiry:
        try:
            expiry = date.fromisoformat(insurance_expiry)
            days_left = (expiry - date.today()).days
            if days_left < 0:
                return "red"
            if days_left <= _INS_URGENT_DAYS:
                return "red"
            if days_left <= _INS_WARN_DAYS:
                return "yellow"
        except ValueError:
            pass

    # Conditional rating from census → yellow (after insurance passed)
    if census and not census.get("error"):
        if (census.get("safety_rating") or "").strip() == "Conditional":
            return "yellow"

    return "green"


def check_cdl_expiry(carrier_id: str) -> list[dict]:
    """Steps 157–159: scan all CDLs for this carrier and return alert list."""
    sb = get_supabase()
    rows = (
        sb.table("driver_cdl")
        .select("*")
        .eq("carrier_id", carrier_id)
        .execute()
        .data
    )
    alerts = []
    today = date.today()

    for row in rows:
        if not row.get("cdl_expiry"):
            continue
        expiry = date.fromisoformat(row["cdl_expiry"])
        days_left = (expiry - today).days
        driver_id = row["driver_id"]
        driver_name = row.get("driver_name", driver_id)

        if days_left < 0:
            status = "red"
            msg = f"CDL EXPIRED {abs(days_left)}d ago — {driver_name}"
        elif days_left <= _CDL_URGENT_DAYS:
            status = "red"
            msg = f"CDL expires in {days_left}d — {driver_name} — URGENT"
        elif days_left <= _CDL_WARN_DAYS:
            status = "yellow"
            msg = f"CDL expires in {days_left}d — {driver_name}"
        else:
            status = "green"
            msg = None

        if msg:
            sb.table("driver_cdl").update({
                "cdl_status": status,
                "updated_at": "now()",
            }).eq("id", row["id"]).execute()
            alerts.append({
                "driver_id": driver_id,
                "driver_name": driver_name,
                "cdl_expiry": row["cdl_expiry"],
                "days_left": days_left,
                "status": status,
                "message": msg,
            })
            log_agent("shield", "cdl_alert", carrier_id=carrier_id,
                      payload={"driver_id": driver_id, "days_left": days_left, "status": status})

    return alerts


def run_cdl_sweep() -> dict:
    """Sweep all active carriers for expiring CDLs (Step 157 — daily job)."""
    sb = get_supabase()
    carriers = sb.table("active_carriers").select("id").eq("status", "active").execute().data
    all_alerts: list[dict] = []
    for c in carriers:
        alerts = check_cdl_expiry(c["id"])
        all_alerts.extend(alerts)
    log_agent("shield", "cdl_sweep", payload={"carriers_checked": len(carriers), "alerts": len(all_alerts)})
    return {"carriers_checked": len(carriers), "cdl_alerts": all_alerts}


def enqueue_safety_check(carrier_id: str, dot: str | None, mc: str | None) -> None:
    """Called from intake — runs SAFER + Census + CDL check on new carrier."""
    log_agent("shield", "enqueue", carrier_id=carrier_id, payload={"dot": dot, "mc": mc})
    sb = get_supabase()

    # Pull both data sources in parallel-ish
    safer = fetch_safer(dot)
    census = fetch_census(dot)

    insurance = (
        sb.table("insurance_compliance")
        .select("policy_expiry")
        .eq("carrier_id", carrier_id)
        .single()
        .execute()
        .data
    )
    expiry = insurance.get("policy_expiry") if insurance else None
    light = score(safer, expiry, census)

    # Enrich active_carriers with census data if available
    if census and not census.get("error") and not census.get("stub"):
        enrich: dict[str, Any] = {}
        if census.get("total_power_units"):
            try:
                enrich["fleet_size"] = int(str(census["total_power_units"]).replace(",", ""))
            except ValueError:
                pass
        if census.get("telephone") and not enrich.get("phone"):
            enrich["phone"] = census["telephone"]
        if enrich:
            try:
                sb.table("active_carriers").update(enrich).eq("id", carrier_id).execute()
            except Exception:  # noqa: BLE001
                pass

    try:
        sb.table("insurance_compliance").update(
            {
                "safety_light": light,
                "last_checked_at": "now()",
                "census_safety_rating": (census or {}).get("safety_rating") or None,
            }
        ).eq("carrier_id", carrier_id).execute()
    except Exception as e:  # noqa: BLE001
        log_agent("shield", "update_light", carrier_id=carrier_id, error=str(e))

    log_agent("shield", "check_complete", carrier_id=carrier_id,
              result=light, payload={"census_rating": (census or {}).get("safety_rating")})
    check_cdl_expiry(carrier_id)


def run(payload: dict[str, Any]) -> dict[str, Any]:
    dot = payload.get("dot_number")
    carrier_id = payload.get("carrier_id")
    safer = fetch_safer(dot)
    light = score(safer)
    cdl_alerts = check_cdl_expiry(carrier_id) if carrier_id else []
    log_agent("shield", "run", payload=payload, result=light)
    return {
        "agent": "shield",
        "dot": dot,
        "safety_light": light,
        "safer": safer,
        "cdl_alerts": cdl_alerts,
    }

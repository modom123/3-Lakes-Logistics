"""FMCSA Company Census daily new-entrant ingest.

Uses the open data.transportation.gov Socrata API — no API key required.
Targets newly registered small fleets (1–10 trucks, authorized, no OOS),
added in the last 180 days. Rotates through high-density trucking states
day-by-day for consistent daily coverage.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..logging_service import log_agent

_CENSUS_URL = "https://data.transportation.gov/resource/az4n-8mr2.json"
_TIMEOUT = 25

# Rotate through high-density trucking states by day-of-year
_STATES = [
    "TX", "CA", "FL", "IL", "OH",
    "GA", "PA", "NC", "TN", "MO",
    "IN", "MI", "WI", "MN", "CO",
    "AZ", "VA", "AL", "KY", "LA",
    "SC", "AR", "OK", "NE", "KS",
]

_SELECT = ",".join([
    "dot_number", "legal_name", "dba_name",
    "operating_status", "entity_type",
    "telephone", "phy_city", "phy_state", "phy_zip", "phy_street",
    "mc_mx_ff_number", "total_power_units", "total_drivers",
    "straight_trucks", "tractor_trucks", "trailers",
    "safety_rating", "hm_flag", "carrier_operation",
    "mcs150_form_date", "add_date",
])


def today_state() -> str:
    """Return which state today's pull will target."""
    day_idx = datetime.now(timezone.utc).timetuple().tm_yday
    return _STATES[day_idx % len(_STATES)]


def fetch_new_entrants(limit: int = 50, since_days: int = 180) -> list[dict[str, Any]]:
    """Pull new carrier registrations from FMCSA Census.

    Rotates through states by day-of-year. No API key required.
    Returns raw FMCSA census records.
    """
    state = today_state()
    since_date = (
        datetime.now(timezone.utc) - timedelta(days=since_days)
    ).strftime("%Y-%m-%dT00:00:00.000")

    conditions = [
        "operating_status='AUTHORIZED'",
        "entity_type='CARRIER'",
        "oos_date IS NULL",
        f"phy_state='{state}'",
        "total_power_units >= '1'",
        "total_power_units <= '10'",
        f"add_date >= '{since_date}'",
    ]

    params = {
        "$where": " AND ".join(conditions),
        "$select": _SELECT,
        "$order": "add_date DESC",
        "$limit": str(limit),
    }

    try:
        r = httpx.get(_CENSUS_URL, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        records = r.json() or []
        log_agent(
            "scout", "fmcsa_census_pull",
            payload={"state": state, "since_days": since_days, "fetched": len(records)},
            result=f"fetched {len(records)} new entrants from {state}",
        )
        return records
    except Exception as exc:  # noqa: BLE001
        log_agent("scout", "fmcsa_census_error", result=str(exc)[:200])
        return []


def ingest(limit: int = 50) -> dict[str, Any]:
    """Pull and insert today's new entrants. Called by the daily run endpoint."""
    from ..prospecting import dedupe, scoring
    from ..supabase_client import get_supabase

    records = fetch_new_entrants(limit=limit)
    sb = get_supabase()
    inserted = 0
    state = today_state()

    for rec in records:
        dot = str(rec.get("dot_number") or "").strip()
        mc_raw = rec.get("mc_mx_ff_number") or ""
        mc = mc_raw.replace("MC-", "").replace("MX-", "").replace("FF-", "").strip()
        name = (rec.get("legal_name") or rec.get("dba_name") or "").strip()
        if not name:
            continue
        if dedupe.is_duplicate(dot, mc):
            continue

        def _int(v: Any) -> int:
            try:
                return int(str(v or 0).replace(",", ""))
            except (ValueError, TypeError):
                return 0

        trucks   = _int(rec.get("total_power_units"))
        tractors = _int(rec.get("tractor_trucks"))
        straight = _int(rec.get("straight_trucks"))

        equip_types = []
        if tractors > 0:
            equip_types.append("Tractor-Trailer")
        if straight > 0:
            equip_types.append("Straight Truck")
        if rec.get("hm_flag") == "Y":
            equip_types.append("Hazmat")

        rating = (rec.get("safety_rating") or "Not Rated").strip()
        notes_parts = [f"FMCSA Safety Rating: {rating}"]
        if trucks:
            notes_parts.append(f"Trucks: {trucks}")
        if rec.get("total_drivers"):
            notes_parts.append(f"Drivers: {rec['total_drivers']}")
        op_map = {"I": "Interstate", "A": "Intrastate", "H": "Intrastate HM"}
        op = op_map.get(rec.get("carrier_operation", ""), "")
        if op:
            notes_parts.append(f"Op: {op}")
        if rec.get("add_date"):
            notes_parts.append(f"DOT registered: {str(rec['add_date'])[:10]}")

        row: dict[str, Any] = {
            "business_name": name,
            "company_name":  name,
            "source":        "FMCSA",
            "source_ref":    dot,
            "status":        "New",
            "stage":         "new",
            "notes":         " · ".join(notes_parts),
        }
        if dot:                      row["dot_number"]      = dot
        if mc:                       row["mc_number"]       = mc
        if rec.get("telephone"):     row["phone"]           = str(rec["telephone"]).strip()
        if rec.get("phy_city"):      row["city"]            = str(rec["phy_city"]).strip()
        if rec.get("phy_state"):     row["state"]           = str(rec["phy_state"]).strip()
        if trucks:                   row["fleet_size"]      = trucks
        if equip_types:              row["equipment_type"]  = equip_types[0]
        if equip_types:              row["equipment_types"] = equip_types

        row["score"] = scoring.score_lead(row)
        sb.table("leads").insert(row).execute()
        inserted += 1

    log_agent(
        "vance", "fmcsa_ingest",
        payload={"fetched": len(records), "inserted": inserted, "state": state},
        result=f"{inserted}/{len(records)} inserted from {state}",
    )
    return {"fetched": len(records), "inserted": inserted, "state": state}

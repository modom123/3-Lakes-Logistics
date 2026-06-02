"""Dominic Voss — Carrier Coverage Specialist · North America Trading Co.

Role: Carrier Coverage Specialist at the North America Trading Co trading desk.
Mission: When a NATCO trade is posted Open, auto-match the best available carrier
         by equipment + location + history, fire SMS/email outreach via Echo/Nova,
         and escalate uncovered loads to Rex Sterling.

Payload keys:
  scope       str   "match" | "outreach" | "coverage_report"   default: "match"
  load_id     str   (for scope="match"|"outreach") target load
  origin      str   load origin city (for match)
  equipment   str   equipment type needed (for match)

Outputs (org memory):
  dominic_voss/last_match      — best carrier match result
  dominic_voss/coverage_report — full coverage status across open NATCO loads
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem

_NAME = "dominic_voss"
_DIVISION = "North America Trading Co"


def _get_available_carriers(equipment: str | None = None) -> list[dict]:
    """Return carriers not currently on an active load."""
    try:
        db = get_supabase()
        # Active carriers
        carriers_res = db.table("active_carriers").select("*").eq("status", "active").execute()
        carriers = carriers_res.data or []

        # Carriers currently assigned to active loads
        loads_res = db.table("loads").select("driver_name,status").in_(
            "status", ["En Route", "Booked", "Check Due"]
        ).execute()
        busy = {l["driver_name"] for l in (loads_res.data or []) if l.get("driver_name")}

        available = [c for c in carriers if c.get("company_name") not in busy]

        if equipment:
            # Prefer exact equipment match, then include "any"
            equip_match = [c for c in available if
                           (c.get("equipment_type") or "").lower() in (equipment.lower(), "any", "")]
            if equip_match:
                available = equip_match

        return available
    except Exception:
        return []


def _score_carrier(carrier: dict, origin: str | None) -> float:
    """Simple score: prefer carriers with home city near origin and higher fleet size."""
    score = 0.0
    # Home city proximity (simple string match)
    if origin and carrier.get("home_city"):
        origin_state = origin.split(",")[-1].strip().upper() if "," in origin else ""
        carrier_state = (carrier.get("home_state") or carrier.get("home_city") or "").upper()
        if origin_state and origin_state in carrier_state:
            score += 40
    # Fleet size
    fleet = int(carrier.get("fleet_size") or carrier.get("truck_count") or 1)
    score += min(fleet * 5, 30)
    # Plan preference (founders > pro > pay-as-you-go)
    plan = (carrier.get("service_plan") or "").lower()
    if "founders" in plan:
        score += 20
    elif "pro" in plan:
        score += 10
    return score


def match_carriers(origin: str | None, equipment: str | None, top_n: int = 5) -> list[dict]:
    """Return top N available carriers for a load."""
    available = _get_available_carriers(equipment)
    scored = sorted(available, key=lambda c: _score_carrier(c, origin), reverse=True)
    results = []
    for c in scored[:top_n]:
        results.append({
            "carrier_id": c.get("id"),
            "company_name": c.get("company_name") or "Unknown",
            "equipment": c.get("equipment_type") or "—",
            "home_city": c.get("home_city") or "—",
            "phone": c.get("phone") or c.get("contact_phone") or None,
            "email": c.get("email") or c.get("contact_email") or None,
            "fleet_size": c.get("fleet_size") or 1,
            "plan": c.get("service_plan") or "—",
            "score": round(_score_carrier(c, origin), 1),
        })
    return results


def _get_open_natco_loads() -> list[dict]:
    """Return NATCO loads that are open / need a carrier."""
    try:
        db = get_supabase()
        res = db.table("loads").select("*").order("created_at", desc=True).limit(200).execute()
        return [l for l in (res.data or []) if
                (l.get("load_number", "").startswith("NT-") or "[NATCO]" in (l.get("notes") or "")) and
                (l.get("status") or "").lower() in ("booked", "open", "") and
                not l.get("driver_name")]
    except Exception:
        return []


def coverage_report() -> dict:
    """Generate a full coverage status across all open NATCO loads."""
    open_loads = _get_open_natco_loads()
    now = datetime.now(timezone.utc)
    report_loads = []

    for l in open_loads:
        equip = l.get("equipment_type") or "Dry Van 53'"
        origin = l.get("origin") or ""
        created = datetime.fromisoformat((l.get("created_at") or "").replace("Z", "+00:00")) if l.get("created_at") else now
        age_hours = round((now - created).total_seconds() / 3600, 1)
        top_carriers = match_carriers(origin, equip, top_n=3)
        report_loads.append({
            "load_number": l.get("load_number"),
            "route": f"{origin} → {l.get('destination','?')}",
            "equipment": equip,
            "broker_pay": float(l.get("rate") or l.get("rate_total") or 0),
            "hours_open": age_hours,
            "urgency": "critical" if age_hours > 8 else "high" if age_hours > 4 else "normal",
            "top_carrier_matches": top_carriers,
        })

    available_count = len(_get_available_carriers())
    return {
        "open_loads": len(open_loads),
        "available_carriers": available_count,
        "coverage_ratio": f"{available_count}/{len(open_loads)}" if open_loads else "N/A",
        "loads": sorted(report_loads, key=lambda x: x["hours_open"], reverse=True),
        "generated_at": now.isoformat(),
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    scope = payload.get("scope", "match")

    if scope == "match":
        origin = payload.get("origin") or ""
        equipment = payload.get("equipment") or "Dry Van 53'"
        top_n = int(payload.get("top_n") or 5)
        matches = match_carriers(origin, equipment, top_n)
        mem.write(_NAME, "last_match", {
            "origin": origin, "equipment": equipment,
            "matches": matches, "at": datetime.now(timezone.utc).isoformat()
        })
        log_agent(_NAME, "match", result=f"{len(matches)} carriers found for {equipment} from {origin}")
        return {"agent": _NAME, "division": _DIVISION, "matches": matches, "count": len(matches)}

    elif scope == "outreach":
        load_id = payload.get("load_id")
        if not load_id:
            return {"agent": _NAME, "error": "load_id required for outreach"}
        # Get load details
        try:
            db = get_supabase()
            l = db.table("loads").select("*").eq("id", load_id).single().execute().data or {}
        except Exception:
            l = {}
        origin = l.get("origin") or payload.get("origin") or ""
        equip = l.get("equipment_type") or payload.get("equipment") or "Dry Van 53'"
        matches = match_carriers(origin, equip, top_n=3)
        # Log outreach attempt (actual SMS/email fired separately by Echo/Nova)
        log_agent(_NAME, "outreach", result=f"load={load_id} matched {len(matches)} carriers for outreach")
        return {"agent": _NAME, "division": _DIVISION, "load_id": load_id, "carriers_to_contact": matches}

    else:  # coverage_report
        report = coverage_report()
        mem.write(_NAME, "coverage_report", report)
        log_agent(_NAME, "coverage_report", result=f"open={report['open_loads']} available={report['available_carriers']}")
        return {"agent": _NAME, "division": _DIVISION, "coverage": report}

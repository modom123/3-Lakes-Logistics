"""Naomi Kensington — Head Predictive Targeting (IEBC Step 59).
Scores and ranks leads using fleet size, equipment type, geographic
demand, existing score, and pipeline velocity signals. Surfaces the
top targets for Vance / Isabella to action immediately.
"""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase

# Equipment types that match 3 Lakes' highest-demand lanes
_HIGH_VALUE_EQUIPMENT = {"dry van", "reefer", "flatbed", "step deck", "power only"}

# Status weights — how close is the lead to converting?
_STATUS_WEIGHT: dict[str, float] = {
    "Warm":       1.5,
    "Contacted":  1.2,
    "New":        1.0,
    "Cold":       0.5,
    "Converted":  0.0,  # already done
    "Dead":       0.0,
}


def _fleet_score(fleet_size: int | None) -> float:
    """Larger fleets = more loads = higher value."""
    if not fleet_size:
        return 0.5
    if fleet_size >= 10:
        return 2.0
    if fleet_size >= 5:
        return 1.5
    if fleet_size >= 2:
        return 1.0
    return 0.8


def _equipment_score(equip: str | None) -> float:
    if not equip:
        return 0.5
    return 1.5 if equip.lower() in _HIGH_VALUE_EQUIPMENT else 1.0


def score_lead(lead: dict[str, Any]) -> float:
    base = float(lead.get("score") or 5)
    status_w = _STATUS_WEIGHT.get(lead.get("status") or "New", 1.0)
    fleet_w = _fleet_score(lead.get("fleet_size"))
    equip_w = _equipment_score(lead.get("equipment_type"))
    return round(base * status_w * fleet_w * equip_w, 2)


def rank_leads(limit: int = 100, min_score: float = 0) -> dict[str, Any]:
    sb = get_supabase()
    rows = (
        sb.table("leads")
        .select("id,business_name,contact_name,phone,equipment_type,fleet_size,status,score,city,state")
        .not_.in_("status", ["Converted", "Dead"])
        .limit(limit)
        .execute()
        .data or []
    )

    scored: list[dict[str, Any]] = []
    for lead in rows:
        ps = score_lead(lead)
        if ps < min_score:
            continue
        scored.append({
            "lead_id": lead["id"],
            "business_name": lead.get("business_name"),
            "contact_name": lead.get("contact_name"),
            "phone": lead.get("phone"),
            "status": lead.get("status"),
            "equipment_type": lead.get("equipment_type"),
            "fleet_size": lead.get("fleet_size"),
            "location": f"{lead.get('city') or ''}, {lead.get('state') or ''}".strip(", "),
            "base_score": lead.get("score"),
            "predictive_score": ps,
        })

    scored.sort(key=lambda x: x["predictive_score"], reverse=True)

    tier_a = [s for s in scored if s["predictive_score"] >= 10]
    tier_b = [s for s in scored if 5 <= s["predictive_score"] < 10]
    tier_c = [s for s in scored if s["predictive_score"] < 5]

    return {
        "leads_analyzed": len(rows),
        "leads_scored": len(scored),
        "tier_a_count": len(tier_a),
        "tier_b_count": len(tier_b),
        "tier_c_count": len(tier_c),
        "top_targets": scored[:10],
        "handoff": "Pass top_targets to Vance for immediate call or Isabella for campaign.",
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    limit = int(payload.get("limit", 200))
    min_score = float(payload.get("min_score", 0))
    result = rank_leads(limit=limit, min_score=min_score)
    log_agent(
        "naomi", "predictive_rank",
        payload={"limit": limit},
        result=f"analyzed={result['leads_analyzed']} tier_a={result['tier_a_count']} tier_b={result['tier_b_count']}",
    )
    return {"agent": "naomi", **result}

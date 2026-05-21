"""Naomi Kensington — Head Predictive Targeting (IEBC Step 59).

Two-stage intelligence cycle:
  Stage 1 — Exchange with Alexander Wright
    Call alexander.run() to get geographic demand signals (hot states) from
    the DOT/FMCSA Company Census dataset. States with the highest carrier
    density become demand multipliers in the scoring model.

  Stage 2 — FMCSA Census Pull
    For each top hot state, query the FMCSA census directly for authorized
    carriers not already in the leads table. These are fresh, unscored
    prospects that Alexander's market intelligence flagged.

  Stage 3 — Unified Scoring
    Score existing Supabase leads + fresh FMCSA prospects together using
    the composite model (fleet size, equipment, status, geographic demand).
    Leads in hot states get a demand multiplier from Alexander's signal.

  Output — Tier A / B / C ranked list
    Tier A (score >= 10) → Vance call list
    Tier B (score 5-9)   → Isabella campaign
    Tier C (score < 5)   → nurture / archive
"""
from __future__ import annotations

from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import alexander as alexander_agent
from . import memory as mem

_FMCSA_BASE = "https://data.transportation.gov/resource/az4n-8mr2.json"
_TIMEOUT = 20

_HIGH_VALUE_EQUIPMENT = {"dry van", "reefer", "flatbed", "step deck", "power only"}

_STATUS_WEIGHT: dict[str, float] = {
    "Warm":      1.5,
    "Contacted": 1.2,
    "New":       1.0,
    "Cold":      0.5,
    "Converted": 0.0,
    "Dead":      0.0,
}


# ── Stage 1: Alexander exchange ───────────────────────────────────────────────

def _get_score_weights() -> dict[str, Any]:
    """Read Naomi's learned scoring weights from memory (updated by Vance feedback)."""
    stored = mem.recall_value("naomi", "score_weights")
    if stored:
        return stored
    # Defaults — Vance outcomes will refine these
    return {
        "min_fleet_for_tier_a": 5,
        "geo_top_n": 5,
        "hot_state_max_multiplier": 1.5,
    }


def _get_hot_states(top_n: int = 5) -> dict[str, float]:
    """Call Alexander Wright and extract top-N states by carrier density.
    Returns {state_abbr: demand_multiplier} — highest density = highest multiplier.
    Falls back to empty dict if Alexander / DOT API unavailable.
    """
    try:
        # First check if Alexander already ran recently — use memory as fast path
        cached = mem.recall_value("alexander", "hot_states")
        if cached and isinstance(cached, dict):
            # Already have fresh data from Alexander — compute multipliers from cache
            total = sum(cached.values()) or 1
            ranked = sorted(cached.items(), key=lambda x: x[1], reverse=True)[:top_n]
            multipliers: dict[str, float] = {}
            for i, (state, _) in enumerate(ranked):
                m = round(1.1 + 0.4 * (1 - i / max(top_n - 1, 1)), 2)
                multipliers[state.upper()] = m
            mem.log_interaction("naomi", "alexander", "query",
                payload={"source": "memory_cache"},
                result={"states_retrieved": len(multipliers)},
                outcome="success", outcome_notes="Read from org brain cache")
            return multipliers

        intel = alexander_agent.run({"limit": 200})
        geo: dict[str, int] = intel.get("geographic_distribution") or {}
        if not geo:
            return {}
        total = sum(geo.values()) or 1
        # Sort by volume, take top N
        ranked = sorted(geo.items(), key=lambda x: x[1], reverse=True)[:top_n]
        # Scale multiplier: #1 state = 1.5x, last state = 1.1x
        multipliers_live: dict[str, float] = {}
        for i, (state, count) in enumerate(ranked):
            m = round(1.1 + 0.4 * (1 - i / max(top_n - 1, 1)), 2)
            multipliers_live[state.upper()] = m
        mem.log_interaction("naomi", "alexander", "query",
            payload={"source": "live_run"},
            result={"states_retrieved": len(multipliers_live)},
            outcome="success", outcome_notes=f"Live Alexander call: top state {ranked[0][0] if ranked else 'N/A'}")
        return multipliers_live
    except Exception:
        return {}


# ── Stage 2: FMCSA census pull ────────────────────────────────────────────────

def _fmcsa_fetch(where: str, limit: int = 50) -> list[dict]:
    settings = get_settings()
    params: dict[str, Any] = {
        "$where": where,
        "$select": (
            "dot_number,legal_name,dba_name,telephone,phy_city,phy_state,"
            "total_power_units,total_drivers,tractor_trucks,straight_trucks,"
            "equipment_type,safety_rating,operating_status,oos_date,mc_mx_ff_number"
        ),
        "$order": "total_power_units DESC",
        "$limit": limit,
    }
    headers: dict[str, str] = {}
    if settings.dot_api_key:
        headers["X-App-Token"] = settings.dot_api_key
    try:
        r = httpx.get(_FMCSA_BASE, params=params, headers=headers, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json() or []
    except Exception:
        return []


def _int(val: Any) -> int:
    try:
        return int(str(val).replace(",", "")) if val else 0
    except (ValueError, TypeError):
        return 0


def _pull_fmcsa_prospects(hot_states: dict[str, float], per_state: int = 30) -> list[dict[str, Any]]:
    """Fetch authorized carriers from hot states not already in leads table."""
    if not hot_states:
        return []

    sb = get_supabase()
    # Get existing DOT numbers to deduplicate
    existing = sb.table("leads").select("dot_number").not_.is_("dot_number", "null").execute()
    known_dots = {str(r["dot_number"]) for r in (existing.data or [])}

    prospects: list[dict[str, Any]] = []
    for state in list(hot_states.keys())[:3]:  # cap at 3 states to stay within rate limits
        where = (
            f"phy_state='{state}' AND operating_status='AUTHORIZED' "
            f"AND oos_date IS NULL AND entity_type='CARRIER' "
            f"AND total_power_units >= '1' AND total_power_units <= '50'"
        )
        rows = _fmcsa_fetch(where, limit=per_state)
        for row in rows:
            dot = str(row.get("dot_number") or "").strip()
            if dot in known_dots or not dot:
                continue
            mc_raw = str(row.get("mc_mx_ff_number") or "")
            prospects.append({
                "source": "fmcsa_census",
                "dot_number": dot,
                "mc_number": mc_raw.replace("MC-", "").replace("MX-", "").strip(),
                "business_name": (row.get("legal_name") or row.get("dba_name") or "").strip(),
                "phone": (row.get("telephone") or "").strip(),
                "city": (row.get("phy_city") or "").strip(),
                "state": state,
                "fleet_size": _int(row.get("total_power_units")) or _int(row.get("tractor_trucks")) + _int(row.get("straight_trucks")),
                "equipment_type": "Dry Van" if _int(row.get("tractor_trucks")) > 0 else "Straight Truck",
                "status": "New",
                "score": 5,  # neutral base — model will re-score
                "safety_rating": row.get("safety_rating") or "Not Rated",
            })
            known_dots.add(dot)  # prevent dupes across states

    return prospects


# ── Stage 3: Unified scoring ──────────────────────────────────────────────────

def _geo_multiplier(state: str | None, hot_states: dict[str, float]) -> float:
    if not state or not hot_states:
        return 1.0
    return hot_states.get((state or "").upper(), 1.0)


def _fleet_score(fleet_size: int | None) -> float:
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


def _score(lead: dict[str, Any], hot_states: dict[str, float]) -> float:
    base        = float(lead.get("score") or 5)
    status_w    = _STATUS_WEIGHT.get(lead.get("status") or "New", 1.0)
    fleet_w     = _fleet_score(lead.get("fleet_size"))
    equip_w     = _equipment_score(lead.get("equipment_type"))
    geo_w       = _geo_multiplier(lead.get("state"), hot_states)
    return round(base * status_w * fleet_w * equip_w * geo_w, 2)


def rank_leads(limit: int = 200, min_score: float = 0, include_fmcsa: bool = True) -> dict[str, Any]:
    sb = get_supabase()

    # Stage 1 — get market intelligence from Alexander
    hot_states = _get_hot_states(top_n=5)

    # Pull existing Supabase leads
    rows = (
        sb.table("leads")
        .select("id,business_name,contact_name,phone,equipment_type,fleet_size,status,score,city,state,dot_number")
        .not_.in_("status", ["Converted", "Dead"])
        .limit(limit)
        .execute()
        .data or []
    )

    # Stage 2 — fresh FMCSA prospects from hot states
    fmcsa_prospects: list[dict[str, Any]] = []
    if include_fmcsa and hot_states:
        fmcsa_prospects = _pull_fmcsa_prospects(hot_states, per_state=25)

    # Stage 3 — score everything together
    all_leads = list(rows) + fmcsa_prospects
    scored: list[dict[str, Any]] = []
    for lead in all_leads:
        ps = _score(lead, hot_states)
        if ps < min_score:
            continue
        geo_boost = _geo_multiplier(lead.get("state"), hot_states)
        scored.append({
            "lead_id":          lead.get("id") or lead.get("dot_number"),
            "business_name":    lead.get("business_name"),
            "contact_name":     lead.get("contact_name"),
            "phone":            lead.get("phone"),
            "dot_number":       lead.get("dot_number"),
            "status":           lead.get("status"),
            "equipment_type":   lead.get("equipment_type"),
            "fleet_size":       lead.get("fleet_size"),
            "location":         f"{lead.get('city') or ''}, {lead.get('state') or ''}".strip(", "),
            "base_score":       lead.get("score"),
            "predictive_score": ps,
            "geo_multiplier":   geo_boost,
            "source":           lead.get("source", "supabase"),
            "safety_rating":    lead.get("safety_rating"),
        })

    scored.sort(key=lambda x: x["predictive_score"], reverse=True)

    tier_a = [s for s in scored if s["predictive_score"] >= 10]
    tier_b = [s for s in scored if 5 <= s["predictive_score"] < 10]
    tier_c = [s for s in scored if s["predictive_score"] < 5]

    return {
        "leads_analyzed":       len(rows),
        "fmcsa_prospects_added": len(fmcsa_prospects),
        "total_scored":         len(scored),
        "tier_a_count":         len(tier_a),
        "tier_b_count":         len(tier_b),
        "tier_c_count":         len(tier_c),
        "hot_states":           hot_states,
        "top_targets":          scored[:15],
        "alexander_powered":    bool(hot_states),
        "handoff": (
            f"Tier A ({len(tier_a)} leads) → Vance call list. "
            f"Tier B ({len(tier_b)} leads) → Isabella campaign. "
            f"Hot states: {', '.join(list(hot_states.keys())[:3]) or 'N/A'}."
        ),
    }


def _learn_from_vance() -> dict[str, Any]:
    """Read Vance call outcomes and adjust scoring weights if Tier A accuracy is low."""
    outcomes = mem.recall_value("vance", "call_outcomes") or {}
    tier_a_calls   = int(outcomes.get("tier_a_calls", 0))
    tier_a_connected = int(outcomes.get("tier_a_connected", 0))
    weights = _get_score_weights()

    if tier_a_calls >= 10:
        accuracy = tier_a_connected / tier_a_calls
        if accuracy < 0.4:
            # Tier A threshold too low — raise bar
            weights["min_fleet_for_tier_a"] = min(10, weights.get("min_fleet_for_tier_a", 5) + 1)
            mem.remember("naomi", "score_weights", weights, confidence=0.65,
                summary=f"Raised Tier A bar: Vance Tier A connect rate only {accuracy:.0%}")
        elif accuracy > 0.7:
            # Model performing well — lower bar slightly to capture more leads
            weights["min_fleet_for_tier_a"] = max(2, weights.get("min_fleet_for_tier_a", 5) - 1)
            mem.remember("naomi", "score_weights", weights, confidence=0.75,
                summary=f"Lowered Tier A bar: Vance Tier A connect rate {accuracy:.0%}")
    return weights


def run(payload: dict[str, Any]) -> dict[str, Any]:
    limit         = int(payload.get("limit", 200))
    min_score     = float(payload.get("min_score", 0))
    include_fmcsa = bool(payload.get("include_fmcsa", True))

    # Learn from Vance outcomes before scoring
    _learn_from_vance()

    result = rank_leads(limit=limit, min_score=min_score, include_fmcsa=include_fmcsa)
    log_agent(
        "naomi", "predictive_rank",
        payload={"limit": limit, "include_fmcsa": include_fmcsa},
        result=(
            f"analyzed={result['leads_analyzed']} fmcsa_new={result['fmcsa_prospects_added']} "
            f"tier_a={result['tier_a_count']} hot_states={list(result['hot_states'].keys())[:3]}"
        ),
    )

    # Write discoveries to org brain
    mem.remember(
        "naomi", "tier_a_targets",
        {"targets": result["top_targets"][:10], "count": result["tier_a_count"]},
        confidence=0.7,
        summary=f"Tier A: {result['tier_a_count']} leads · hot states: {', '.join(list(result['hot_states'].keys())[:3])}",
    )
    mem.remember(
        "naomi", "tier_b_targets",
        {"count": result["tier_b_count"], "hot_states": result["hot_states"]},
        confidence=0.65,
        summary=f"Tier B: {result['tier_b_count']} leads ready for Isabella campaign",
    )
    mem.remember(
        "org", "lead_intelligence",
        {
            "tier_a_count":   result["tier_a_count"],
            "tier_b_count":   result["tier_b_count"],
            "hot_states":     result["hot_states"],
            "fmcsa_new":      result["fmcsa_prospects_added"],
        },
        confidence=0.7,
        source_agent="naomi",
        summary=f"Lead pipeline: {result['tier_a_count']} Tier A, {result['tier_b_count']} Tier B",
    )
    mem.log_interaction("naomi", "isabella", "handoff",
        payload={"tier_b_count": result["tier_b_count"]},
        result={"status": "tier_b_written_to_memory"},
        outcome="success",
        outcome_notes=f"Isabella should read naomi/tier_b_targets from org brain",
    )
    return {"agent": "naomi", **result}

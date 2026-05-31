"""Alexander Wright — VP Market Intelligence (IEBC Step 55).

Queries the FMCSA Company Census (4.44M carriers, 147 fields) via the
US DOT open data API to build competitive market intelligence for
3 Lakes Logistics.

Dataset: data.transportation.gov/resource/az4n-8mr2.json
  Same dataset used by the Shield safety lookup and FMCSA prospect search.

Intelligence outputs (consumed by Naomi for lead targeting):
  - geographic_distribution: {state: carrier_count} — top 15 states by
    authorized carrier density. Naomi uses this to apply demand multipliers.
  - fleet_capacity_by_state: {state: total_power_units} — actual truck
    capacity in market. High units = high competition but also high demand.
  - top_states_ranked: ordered list of (state, count) tuples for Naomi.

Set DOT_API_KEY in Render env vars (free Socrata app token).
"""
from __future__ import annotations

from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from . import memory as mem

_BASE = "https://data.transportation.gov/resource/az4n-8mr2.json"
_TIMEOUT = 20

# FMCSA census fields used for market intelligence
_INTEL_SELECT = ",".join([
    "dot_number",
    "phy_state",
    "phy_city",
    "total_power_units",
    "total_drivers",
    "tractor_trucks",
    "straight_trucks",
    "entity_type",
    "operating_status",
    "carrier_operation",
    "safety_rating",
])


def _int(val: Any) -> int:
    try:
        return int(str(val).replace(",", "")) if val else 0
    except (ValueError, TypeError):
        return 0


def _fetch(params: dict) -> list[dict[str, Any]]:
    settings = get_settings()
    headers: dict[str, str] = {}
    if settings.dot_api_key:
        headers["X-App-Token"] = settings.dot_api_key
    try:
        r = httpx.get(_BASE, params=params, headers=headers, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json() or []
    except Exception as exc:
        raise RuntimeError(f"DOT/FMCSA API error: {exc}") from exc


def analyze_market(limit: int = 200) -> dict[str, Any]:
    """Pull FMCSA census sample and build geographic demand intelligence."""
    raw = _fetch({
        "$select": _INTEL_SELECT,
        "$where": "operating_status='AUTHORIZED' AND oos_date IS NULL AND entity_type='CARRIER'",
        "$order": "total_power_units DESC",
        "$limit": limit,
    })

    if not raw:
        return {
            "records_fetched": 0,
            "geographic_distribution": {},
            "fleet_capacity_by_state": {},
            "top_states_ranked": [],
            "note": "No data — check DOT_API_KEY and network access to data.transportation.gov",
        }

    # Build state-level aggregations
    state_count: dict[str, int] = {}         # carrier count per state
    state_capacity: dict[str, int] = {}      # total power units per state
    interstate_count: dict[str, int] = {}    # interstate carriers (best targets)
    total_units = 0

    for row in raw:
        state = (row.get("phy_state") or "").strip().upper()
        if not state or len(state) != 2:
            continue
        units = _int(row.get("total_power_units"))
        is_interstate = row.get("carrier_operation", "").upper() == "I"

        state_count[state] = state_count.get(state, 0) + 1
        state_capacity[state] = state_capacity.get(state, 0) + units
        if is_interstate:
            interstate_count[state] = interstate_count.get(state, 0) + 1
        total_units += units

    top_states = sorted(state_count.items(), key=lambda x: x[1], reverse=True)[:15]
    top_interstate = sorted(interstate_count.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "records_fetched": len(raw),
        "total_power_units_sampled": total_units,
        # Primary output consumed by Naomi for demand multipliers
        "geographic_distribution": dict(top_states),
        "fleet_capacity_by_state": {s: state_capacity.get(s, 0) for s, _ in top_states},
        "interstate_carriers_by_state": dict(top_interstate),
        "top_states_ranked": top_states,
        "top_state_by_volume": top_states[0][0] if top_states else None,
        "top_state_by_capacity": max(state_capacity, key=state_capacity.get) if state_capacity else None,
        "intelligence_note": (
            f"Top market: {top_states[0][0] if top_states else 'N/A'} "
            f"({top_states[0][1] if top_states else 0} authorized carriers in sample). "
            "Naomi uses geographic_distribution for demand multipliers."
        ),
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    limit = int(payload.get("limit", 200))
    # Pull CC Gulley's strategic plan and any live directive — shapes market priorities
    cso_plan = mem.recall_value("cc_gulley", "strategic_plan") or {}
    priority_markets = cso_plan.get("priority_markets", [])
    directive = mem.recall_value("cc_gulley", "directive_to_alexander") or {}
    if directive:
        # Directive overrides / extends plan-level market focus
        if directive.get("priority_markets"):
            priority_markets = directive["priority_markets"]
    try:
        result = analyze_market(limit=limit)
        if priority_markets:
            result["cso_priority_markets"] = priority_markets
        if directive:
            result["cso_directive"] = directive.get("instruction", "")
            result["cso_directive_focus"] = directive.get("focus", "")
        top = result.get("top_state_by_volume") or "N/A"
        log_agent(
            "alexander", "market_intel",
            payload={"limit": limit},
            result=f"records={result['records_fetched']} top_state={top} units={result.get('total_power_units_sampled', 0)}",
        )
        # Write to org brain — Naomi and Victoria read this
        if result.get("geographic_distribution"):
            mem.remember(
                "alexander", "hot_states",
                result["geographic_distribution"],
                confidence=0.6,
                summary=f"Top market: {result.get('top_state_by_volume','?')} · {result['records_fetched']} carriers sampled",
            )
            mem.remember(
                "org", "market_intel",
                {
                    "hot_states":          result["geographic_distribution"],
                    "fleet_capacity":      result.get("fleet_capacity_by_state", {}),
                    "interstate_carriers": result.get("interstate_carriers_by_state", {}),
                    "top_state":           result.get("top_state_by_volume"),
                },
                confidence=0.6,
                source_agent="alexander",
                summary=f"FMCSA census market snapshot — {result['records_fetched']} authorized carriers",
            )
            mem.log_interaction(
                "alexander", "org", "broadcast",
                payload={"limit": limit},
                result={"hot_states_written": len(result["geographic_distribution"])},
                outcome="success",
                outcome_notes=f"Top state: {result.get('top_state_by_volume')}",
            )
        mem.log_interaction(
            "alexander", "cc_gulley", "report",
            payload={"priority_markets": priority_markets},
            result={"top_state": result.get("top_state_by_volume"), "records": result.get("records_fetched", 0)},
            outcome="success",
            outcome_notes=f"Market intel run complete · directive applied: {bool(directive)}",
        )
        return {"agent": "alexander", **result}
    except RuntimeError as exc:
        log_agent("alexander", "market_intel", payload={}, result=f"ERROR: {exc}")
        mem.log_interaction("alexander", "org", "broadcast", payload={}, result={"error": str(exc)}, outcome="failed")
        return {"agent": "alexander", "error": str(exc), "records_fetched": 0, "geographic_distribution": {}}

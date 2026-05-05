"""Sonny — Steps 23-24. Load board sniper across all 15 sources."""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from ..prospecting.loadboard_clients import SearchParams, search_all

LOAD_BOARD_SOURCES = [
    "dat", "truckstop", "123loadboard", "truckerpath", "direct_freight",
    "convoy",            # inventory now served via DAT (acquired July 2025)
    "uber_freight", "cargo_chief", "loadsmart", "newtrul",
    "flock_freight", "j_b_hunt_360", "coyote_go", "arrive_logistics", "echo_global",
]


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Step 23: Fetch loads matching a truck's weight + trailer + HOS window.

    Expected payload keys:
        truck_id, trailer_type, max_weight_lbs,
        origin_state, max_deadhead_mi, hos_hours_remaining
    """
    params = SearchParams(
        origin_state=payload.get("origin_state", ""),
        trailer_type=payload.get("trailer_type", "dry_van"),
        max_weight_lbs=int(payload.get("max_weight_lbs") or 45000),
        max_deadhead_mi=int(payload.get("max_deadhead_mi") or 150),
        min_rate_per_mile=float(payload.get("min_rate_per_mile") or 2.10),
        hos_hours_remaining=float(payload.get("hos_hours_remaining") or 11.0),
    )

    if not params.origin_state:
        return {"agent": "sonny", "status": "error", "error": "origin_state required",
                "matched_loads": [], "sources_queried": LOAD_BOARD_SOURCES}

    loads = search_all(params)
    matched = filter_by_equipment(
        [l.__dict__ for l in loads],
        params.max_weight_lbs,
        params.trailer_type,
    )

    log_agent("sonny", "scrape_loads", payload=payload,
              result=f"{len(matched)} loads from {len(LOAD_BOARD_SOURCES)} sources")

    return {
        "agent": "sonny",
        "status": "ok",
        "matched_loads": matched[:50],         # top 50 by $/mi
        "total_found": len(matched),
        "sources_queried": LOAD_BOARD_SOURCES,
    }


def filter_by_equipment(loads: list[dict], max_weight: int, trailer: str) -> list[dict]:
    """Step 24: weight/equipment filter — also accepts loads with no weight set."""
    return [
        l for l in loads
        if (l.get("trailer_type") or "").lower() == trailer.lower()
        and (l.get("weight_lbs") is None or (l.get("weight_lbs") or 0) <= max_weight)
    ]

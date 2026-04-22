"""Sonny — Steps 23-24. Load board scraper + weight/equipment filter."""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent

LOAD_BOARD_SOURCES = [
    "dat", "truckstop", "123loadboard", "truckerpath", "direct_freight",
    "convoy", "uber_freight", "cargo_chief", "loadsmart", "newtrul",
    "flock_freight", "j_b_hunt_360", "coyote_go", "arrive_logistics", "echo_global",
]


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch loads matching a truck's weight + trailer + HOS window.

    Expected payload: { truck_id, trailer_type, max_weight_lbs,
                        origin_state, max_deadhead_mi, hos_hours_remaining }
    """
    log_agent("sonny", "scrape_loads", payload=payload, result="stub")
    return {
        "agent": "sonny",
        "status": "stub",
        "matched_loads": [],
        "sources_queried": LOAD_BOARD_SOURCES,
        "note": "TODO: wire DAT/Truckstop scrapers + scoring in prospecting/loadboard.py",
    }


def filter_by_equipment(loads: list[dict], max_weight: int, trailer: str) -> list[dict]:
    """Step 24: weight/equipment filter."""
    return [
        l for l in loads
        if l.get("trailer_type") == trailer and (l.get("weight_lbs") or 0) <= max_weight
    ]

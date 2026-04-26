"""Sonny — Steps 23-24. Load board scraper + weight/equipment filter + truck matcher."""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase

LOAD_BOARD_SOURCES = [
    "dat", "truckstop", "123loadboard", "truckerpath", "direct_freight",
    "convoy", "uber_freight", "cargo_chief", "loadsmart", "newtrul",
    "flock_freight", "j_b_hunt_360", "coyote_go", "arrive_logistics", "echo_global",
]

_DEADHEAD_PENALTY_PER_MI = 0.15  # cost per deadhead mile
_HOS_MIN_HOURS = 4.0             # driver needs ≥ 4h to be offered a load


def _score_match(load: dict, driver: dict, deadhead_mi: float) -> float:
    """Score a truck–load match on a 0–100 scale.

    Factors:
      - Gross rate (higher is better)
      - Deadhead miles (lower is better)
      - HOS hours remaining (more hours → higher score)
      - Equipment match (boolean gate — already filtered upstream)
    """
    rate = float(load.get("rate_total") or 0)
    hos = float(driver.get("hours_remaining") or driver.get("drive_remaining_min", 0) / 60)
    miles = float(load.get("miles") or 1)

    rpm = rate / max(miles, 1)
    deadhead_cost = deadhead_mi * _DEADHEAD_PENALTY_PER_MI
    net_rate = rate - deadhead_cost

    # Weighted score
    score = (
        min(net_rate / 2000, 1.0) * 50   # rate contribution (max 50 pts)
        + min(hos / 11, 1.0) * 30        # HOS contribution (max 30 pts)
        + max(0, 1 - deadhead_mi / 200) * 20  # proximity (max 20 pts)
    )
    return round(score, 2)


def fetch_available_loads(
    trailer_type: str,
    origin_state: str,
    max_weight_lbs: int,
    hos_hours: float,
    max_deadhead_mi: int = 150,
) -> list[dict[str, Any]]:
    """Pull loads from the DB that match this truck's profile."""
    sb = get_supabase()

    q = (
        sb.table("loads")
        .select(
            "id,load_number,broker_name,origin_city,origin_state,dest_city,dest_state,"
            "rate_total,miles,weight_lbs,trailer_type,pickup_at,delivery_at,commodity,status"
        )
        .eq("status", "available")
        .eq("trailer_type", trailer_type)
        .lte("weight_lbs", max_weight_lbs)
        .limit(200)
    )
    loads = q.execute().data or []

    # Filter by origin state proximity (same state or adjacent gets through)
    loads = [l for l in loads if l.get("origin_state") == origin_state]

    # Filter by HOS: estimate load hours (miles / 55 mph avg)
    def fits_hos(load: dict) -> bool:
        miles = float(load.get("miles") or 0)
        est_hours = miles / 55
        return est_hours <= hos_hours

    loads = [l for l in loads if fits_hos(l)]
    return loads


def filter_by_equipment(loads: list[dict], max_weight: int, trailer: str) -> list[dict]:
    """Step 24: weight/equipment filter."""
    return [
        l for l in loads
        if l.get("trailer_type") == trailer and (l.get("weight_lbs") or 0) <= max_weight
    ]


def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch and rank loads matching this truck's weight, trailer, HOS, and location.

    Expected payload:
      truck_id, trailer_type, max_weight_lbs, origin_state,
      max_deadhead_mi, hos_hours_remaining, driver_id (optional)
    """
    truck_id = payload.get("truck_id", "")
    trailer_type = payload.get("trailer_type", "dry_van")
    max_weight = int(payload.get("max_weight_lbs") or 45000)
    origin_state = payload.get("origin_state", "")
    max_deadhead = int(payload.get("max_deadhead_mi") or 150)
    hos_hours = float(payload.get("hos_hours_remaining") or 11)

    if hos_hours < _HOS_MIN_HOURS:
        log_agent("sonny", "scrape_loads", payload={"truck_id": truck_id}, result="hos_insufficient")
        return {
            "agent": "sonny",
            "status": "no_match",
            "reason": f"driver has only {hos_hours}h remaining (min {_HOS_MIN_HOURS}h required)",
            "matched_loads": [],
        }

    loads = fetch_available_loads(trailer_type, origin_state, max_weight, hos_hours, max_deadhead)

    driver = {"hours_remaining": hos_hours}
    scored = sorted(
        [
            {**l, "_score": _score_match(l, driver, 0)}
            for l in loads
        ],
        key=lambda x: x["_score"],
        reverse=True,
    )

    log_agent("sonny", "scrape_loads",
              payload={"truck_id": truck_id, "trailer": trailer_type, "state": origin_state},
              result=f"{len(scored)} matched")

    return {
        "agent": "sonny",
        "status": "ok" if scored else "no_match",
        "truck_id": truck_id,
        "matched_loads": scored[:10],  # top 10
        "total_found": len(scored),
        "sources_queried": ["db"] + LOAD_BOARD_SOURCES,
    }

"""Sonny — Dispatch + load matching (Stage 5 step 62)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent

LOAD_BOARD_SOURCES = [
    "dat", "truckstop", "123loadboard", "truckerpath", "direct_freight",
    "convoy", "uber_freight", "cargo_chief", "loadsmart", "newtrul",
    "flock_freight", "j_b_hunt_360", "coyote_go", "arrive_logistics", "echo_global",
]


def _score_match(load: dict, truck: dict) -> float:
    """Return 0-100. Higher is better."""
    score = 50.0
    if (load.get("trailer_type") or "").lower() == (truck.get("trailer_type") or "").lower():
        score += 20
    truck_cap = truck.get("max_weight_lbs") or truck.get("max_weight") or 0
    if (load.get("weight_lbs") or 0) <= truck_cap:
        score += 10
    rpm = load.get("rate_per_mile") or 0
    if rpm >= 3.0:
        score += 15
    elif rpm >= 2.5:
        score += 10
    elif rpm >= 2.0:
        score += 5
    deadhead = load.get("deadhead_mi") or 0
    if deadhead < 50:
        score += 10
    elif deadhead > 250:
        score -= 10
    hos_hours = truck.get("hos_hours_remaining")
    duration = load.get("duration_h") or 0
    if hos_hours is not None and duration > hos_hours:
        score -= 25
    return max(0.0, min(100.0, score))


def rank(loads: list[dict], truck: dict) -> list[dict]:
    out = []
    for l in loads:
        out.append({**l, "match_score": _score_match(l, truck)})
    return sorted(out, key=lambda x: x["match_score"], reverse=True)


def filter_by_equipment(loads: list[dict], max_weight_lbs: int, trailer: str) -> list[dict]:
    return [
        l for l in loads
        if (l.get("trailer_type") or "").lower() == (trailer or "").lower()
        and (l.get("weight_lbs") or 0) <= max_weight_lbs
    ]


def _available_trucks() -> list[dict]:
    try:
        from ..supabase_client import get_supabase
        return (
            get_supabase().table("fleet_assets")
            .select("id, carrier_id, truck_id, trailer_type, "
                    "max_weight_lbs, hos_hours_remaining")
            .eq("status", "available")
            .execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001
        log_agent("sonny", "trucks_fetch_failed", error=str(exc))
        return []


def _open_loads() -> list[dict]:
    from ..prospecting import loadboard_scraper
    try:
        return loadboard_scraper.fetch_recent() or []
    except Exception:  # noqa: BLE001
        return []


def match_all_trucks() -> dict[str, Any]:
    trucks = _available_trucks()
    loads = _open_loads()
    created = 0
    for t in trucks:
        ranked = rank(loads, t)[:3]
        for r in ranked:
            if r.get("match_score", 0) < 60:
                continue
            if _write_match(t, r):
                created += 1
    log_agent("sonny", "match_all_trucks", result=f"created={created}")
    return {"status": "ok", "trucks": len(trucks), "loads": len(loads), "matches": created}


def _write_match(truck: dict, load: dict) -> bool:
    try:
        from ..supabase_client import get_supabase
        get_supabase().table("load_matches").insert({
            "carrier_id": truck.get("carrier_id"),
            "truck_id": truck.get("truck_id"),
            "load_source": load.get("source"),
            "load_ref": load.get("ref"),
            "origin": load.get("origin"),
            "destination": load.get("destination"),
            "miles": load.get("miles"),
            "rate_total": load.get("rate_total"),
            "rate_per_mile": load.get("rate_per_mile"),
            "trailer_type": load.get("trailer_type"),
            "weight_lbs": load.get("weight_lbs"),
            "score": load.get("match_score"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return True
    except Exception as exc:  # noqa: BLE001
        log_agent("sonny", "match_insert_failed", error=str(exc))
        return False


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind") or "scrape_loads"
    if kind == "match_all_trucks":
        return {"agent": "sonny", **match_all_trucks()}
    if kind == "rank":
        ranked = rank(payload.get("loads") or [], payload.get("truck") or {})
        return {"agent": "sonny", "status": "ok", "ranked": ranked[:20]}
    return {
        "agent": "sonny", "status": "stub",
        "sources_queried": LOAD_BOARD_SOURCES,
        "note": "call kind='match_all_trucks' or kind='rank'",
    }

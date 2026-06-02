"""Rio — Light Fleet Trip Dispatcher.

Takes pending trips from light_vehicle_trips, finds the best available driver,
and fires the full dispatch workflow (steps 221–240) via the execution engine.

Actions:
  dispatch_pending   find all pending trips and dispatch them
  dispatch_trip      dispatch a single trip_id
  active_trips       list trips currently in progress
  status             dispatch queue stats
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem

_NAME = "rio"


def _db():
    try:
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_best_driver(trip_type: str) -> dict | None:
    sb = _db()
    if not sb:
        return None
    try:
        rows = (
            sb.table("light_vehicle_drivers")
            .select("id,name,phone,vehicle_type,approved_services,total_trips")
            .eq("status", "active")
            .execute()
            .data or []
        )
        eligible = [
            r for r in rows
            if trip_type in (r.get("approved_services") or [])
        ]
        if not eligible:
            return None
        eligible.sort(key=lambda r: r.get("total_trips") or 0)
        return eligible[0]
    except Exception:  # noqa: BLE001
        return None


def dispatch_trip(trip_id: str) -> dict[str, Any]:
    sb = _db()
    if not sb:
        return {"dispatched": False, "error": "db_unavailable"}

    try:
        r = (
            sb.table("light_vehicle_trips")
            .select("*")
            .eq("id", trip_id)
            .maybe_single()
            .execute()
        )
        trip = r.data or {}
    except Exception as e:  # noqa: BLE001
        return {"dispatched": False, "error": str(e)}

    if not trip:
        return {"dispatched": False, "error": "trip_not_found"}

    if trip.get("status") not in ("pending", None):
        return {"dispatched": False, "reason": "trip_not_pending", "status": trip.get("status")}

    trip_type = trip.get("trip_type", "gig")
    driver = _find_best_driver(trip_type)

    if not driver:
        log_agent(_NAME, "no_driver", payload={"trip_id": trip_id, "trip_type": trip_type})
        return {
            "dispatched": False,
            "reason": "no_available_drivers",
            "trip_id": trip_id,
            "trip_type": trip_type,
        }

    driver_id = str(driver["id"])
    assigned_at = _now()

    try:
        sb.table("light_vehicle_trips").update({
            "driver_id": driver_id,
            "status": "assigned",
            "assigned_at": assigned_at,
        }).eq("id", trip_id).execute()

        sb.table("light_vehicle_drivers").update({
            "total_trips": (driver.get("total_trips") or 0) + 1,
        }).eq("id", driver_id).execute()
    except Exception as e:  # noqa: BLE001
        return {"dispatched": False, "error": f"db_update_failed: {e}"}

    mem.remember(
        _NAME, "last_dispatch",
        {"trip_id": trip_id, "driver_id": driver_id, "driver_name": driver.get("name"), "trip_type": trip_type},
        confidence=0.9,
        summary=f"Dispatched {trip_type} trip to {driver.get('name')}",
    )
    log_agent(
        _NAME, "dispatched",
        payload={"trip_id": trip_id, "trip_type": trip_type},
        result=f"driver={driver.get('name')}",
    )

    return {
        "dispatched": True,
        "trip_id": trip_id,
        "trip_type": trip_type,
        "driver_id": driver_id,
        "driver_name": driver.get("name"),
        "driver_phone": driver.get("phone"),
        "assigned_at": assigned_at,
        "pickup_address": trip.get("pickup_address"),
        "dropoff_address": trip.get("dropoff_address"),
        "passenger_name": trip.get("passenger_name"),
    }


def dispatch_pending(limit: int = 20) -> dict[str, Any]:
    sb = _db()
    if not sb:
        return {"error": "db_unavailable"}
    try:
        rows = (
            sb.table("light_vehicle_trips")
            .select("id,trip_type,status")
            .eq("status", "pending")
            .limit(limit)
            .execute()
            .data or []
        )
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}

    results = []
    for row in rows:
        r = dispatch_trip(str(row["id"]))
        results.append(r)

    dispatched = sum(1 for r in results if r.get("dispatched"))
    failed = len(results) - dispatched

    log_agent(_NAME, "dispatch_batch", result=f"dispatched={dispatched} failed={failed}")
    return {
        "pending_found": len(rows),
        "dispatched": dispatched,
        "failed": failed,
        "results": results,
    }


def active_trips() -> dict[str, Any]:
    sb = _db()
    if not sb:
        return {"error": "db_unavailable"}
    try:
        rows = (
            sb.table("light_vehicle_trips")
            .select("id,trip_type,status,driver_id,passenger_name,pickup_address,scheduled_at,assigned_at")
            .in_("status", ["assigned", "in_progress"])
            .order("assigned_at", desc=True)
            .limit(50)
            .execute()
            .data or []
        )
        return {"active_count": len(rows), "trips": rows}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def queue_stats() -> dict[str, Any]:
    sb = _db()
    if not sb:
        return {"error": "db_unavailable"}
    try:
        rows = sb.table("light_vehicle_trips").select("status,trip_type").execute().data or []
        stats: dict[str, int] = {}
        for r in rows:
            stats[r.get("status", "unknown")] = stats.get(r.get("status", "unknown"), 0) + 1
        by_type: dict[str, int] = {}
        for r in rows:
            by_type[r.get("trip_type", "unknown")] = by_type.get(r.get("trip_type", "unknown"), 0) + 1
        return {"by_status": stats, "by_type": by_type, "total": len(rows)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "status")).lower()

    if action == "dispatch_pending":
        result = dispatch_pending(int(payload.get("limit", 20)))
        return {"agent": _NAME, **result}

    if action == "dispatch_trip":
        trip_id = str(payload.get("trip_id", ""))
        if not trip_id:
            return {"agent": _NAME, "error": "trip_id required"}
        return {"agent": _NAME, **dispatch_trip(trip_id)}

    if action == "active_trips":
        return {"agent": _NAME, "action": "active_trips", **active_trips()}

    if action == "status":
        return {"agent": _NAME, "action": "status", **queue_stats()}

    return {"agent": _NAME, "error": f"unknown action: {action}"}

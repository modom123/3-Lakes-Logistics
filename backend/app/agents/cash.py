"""Cash — Light Fleet Settlement & Driver Payouts.

Calculates driver earnings on completed trips, logs to ledger, and marks trips settled.

Fee structure:
  Starter plan  — 15% platform fee  (driver keeps 85%)
  Pro Fleet     — $199/mo + 5% fee  (driver keeps 95%)
  Add-On        — $99/mo + 5% fee   (driver keeps 95%)

Actions:
  settle_trip      settle a single completed trip
  settle_pending   batch-settle all completed/unsettled trips
  earnings         driver earnings summary
  status           settlement queue stats
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem

_NAME = "cash"

# Platform fee rates by driver plan
_FEE_RATES = {
    "starter":    0.15,
    "pro_fleet":  0.05,
    "add_on":     0.05,
    "default":    0.15,
}


def _db():
    try:
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _driver_plan(driver_id: str) -> str:
    sb = _db()
    if not sb or not driver_id:
        return "default"
    try:
        r = (
            sb.table("light_vehicle_drivers")
            .select("plan")
            .eq("id", driver_id)
            .maybe_single()
            .execute()
        )
        return (r.data or {}).get("plan") or "starter"
    except Exception:  # noqa: BLE001
        return "starter"


def settle_trip(trip_id: str) -> dict[str, Any]:
    sb = _db()
    if not sb:
        return {"settled": False, "error": "db_unavailable"}

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
        return {"settled": False, "error": str(e)}

    if not trip:
        return {"settled": False, "error": "trip_not_found"}

    if trip.get("settled_at"):
        return {"settled": False, "reason": "already_settled", "trip_id": trip_id}

    if trip.get("status") not in ("completed", "delivered"):
        return {
            "settled": False,
            "reason": "trip_not_complete",
            "status": trip.get("status"),
            "trip_id": trip_id,
        }

    rate_total = float(trip.get("rate_total") or 0)
    driver_id = trip.get("driver_id")
    trip_type = trip.get("trip_type", "gig")

    plan = _driver_plan(str(driver_id)) if driver_id else "starter"
    fee_rate = _FEE_RATES.get(plan, _FEE_RATES["default"])
    platform_fee = round(rate_total * fee_rate, 2)
    driver_payout = round(rate_total - platform_fee, 2)

    settled_at = _now()

    try:
        sb.table("light_vehicle_trips").update({
            "settled_at": settled_at,
            "driver_payout": driver_payout,
            "platform_fee": platform_fee,
            "status": "settled",
        }).eq("id", trip_id).execute()
    except Exception as e:  # noqa: BLE001
        return {"settled": False, "error": f"db_update_failed: {e}"}

    try:
        from ..atomic_ledger.service import write_event
        from ..atomic_ledger.models import AtomicEvent
        write_event(AtomicEvent(
            event_type="lf_trip_settled",
            event_source="cash_agent",
            logistics_payload={
                "trip_id": trip_id,
                "trip_type": trip_type,
                "driver_id": str(driver_id) if driver_id else None,
            },
            financial_payload={
                "rate_total": rate_total,
                "platform_fee": platform_fee,
                "driver_payout": driver_payout,
                "fee_rate": fee_rate,
                "driver_plan": plan,
            },
        ))
    except Exception:  # noqa: BLE001
        pass

    mem.remember(
        _NAME, "last_settlement",
        {"trip_id": trip_id, "driver_payout": driver_payout, "platform_fee": platform_fee},
        confidence=0.9,
        summary=f"Settled trip {trip_id[:8]} — driver gets ${driver_payout}, platform ${platform_fee}",
    )
    log_agent(_NAME, "settled", payload={"trip_id": trip_id}, result=f"payout=${driver_payout} fee=${platform_fee}")

    return {
        "settled": True,
        "trip_id": trip_id,
        "trip_type": trip_type,
        "driver_id": str(driver_id) if driver_id else None,
        "rate_total": rate_total,
        "platform_fee": platform_fee,
        "fee_rate": fee_rate,
        "driver_payout": driver_payout,
        "driver_plan": plan,
        "settled_at": settled_at,
    }


def settle_pending(limit: int = 50) -> dict[str, Any]:
    sb = _db()
    if not sb:
        return {"error": "db_unavailable"}
    try:
        rows = (
            sb.table("light_vehicle_trips")
            .select("id,status,rate_total,driver_id,trip_type")
            .in_("status", ["completed", "delivered"])
            .is_("settled_at", "null")
            .limit(limit)
            .execute()
            .data or []
        )
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}

    results = [settle_trip(str(r["id"])) for r in rows]
    settled_count = sum(1 for r in results if r.get("settled"))
    total_platform_fee = sum(r.get("platform_fee", 0) for r in results if r.get("settled"))
    total_driver_payouts = sum(r.get("driver_payout", 0) for r in results if r.get("settled"))

    log_agent(_NAME, "batch_settle", result=f"settled={settled_count} platform_fee=${total_platform_fee:.2f}")
    return {
        "trips_found": len(rows),
        "settled": settled_count,
        "total_platform_fee": round(total_platform_fee, 2),
        "total_driver_payouts": round(total_driver_payouts, 2),
        "results": results,
    }


def driver_earnings(driver_id: str, limit: int = 100) -> dict[str, Any]:
    sb = _db()
    if not sb:
        return {"error": "db_unavailable"}
    try:
        rows = (
            sb.table("light_vehicle_trips")
            .select("id,trip_type,rate_total,driver_payout,platform_fee,settled_at,status")
            .eq("driver_id", driver_id)
            .not_.is_("settled_at", "null")
            .order("settled_at", desc=True)
            .limit(limit)
            .execute()
            .data or []
        )
        total_earned = sum(float(r.get("driver_payout") or 0) for r in rows)
        return {
            "driver_id": driver_id,
            "settled_trips": len(rows),
            "total_earned": round(total_earned, 2),
            "trips": rows,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def settlement_stats() -> dict[str, Any]:
    sb = _db()
    if not sb:
        return {"error": "db_unavailable"}
    try:
        rows = (
            sb.table("light_vehicle_trips")
            .select("status,rate_total,driver_payout,platform_fee")
            .execute()
            .data or []
        )
        unsettled = [r for r in rows if r.get("status") in ("completed", "delivered") and not r.get("driver_payout")]
        settled = [r for r in rows if r.get("status") == "settled"]
        total_revenue = sum(float(r.get("rate_total") or 0) for r in settled)
        total_fees = sum(float(r.get("platform_fee") or 0) for r in settled)
        return {
            "unsettled_trips": len(unsettled),
            "settled_trips": len(settled),
            "total_revenue": round(total_revenue, 2),
            "total_platform_fees": round(total_fees, 2),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "status")).lower()

    if action == "settle_trip":
        trip_id = str(payload.get("trip_id", ""))
        if not trip_id:
            return {"agent": _NAME, "error": "trip_id required"}
        return {"agent": _NAME, **settle_trip(trip_id)}

    if action == "settle_pending":
        return {"agent": _NAME, **settle_pending(int(payload.get("limit", 50)))}

    if action == "earnings":
        driver_id = str(payload.get("driver_id", ""))
        if not driver_id:
            return {"agent": _NAME, "error": "driver_id required"}
        return {"agent": _NAME, **driver_earnings(driver_id, int(payload.get("limit", 100)))}

    if action == "status":
        return {"agent": _NAME, "action": "status", **settlement_stats()}

    return {"agent": _NAME, "error": f"unknown action: {action}"}

"""Trading Desk automation API — controls for the auto-trading engine.

POST /api/trading/run-acquisition/   — Jordan scans states, Rex scores, auto-posts
POST /api/trading/run-coverage/      — Casey sweeps uncovered loads, auto-calls
POST /api/trading/run-settlement/    — auto-settle past-delivery loads
POST /api/trading/run-full/          — all three in sequence
GET  /api/trading/live-book/         — open positions with age + risk
GET  /api/trading/pnl-summary/       — P&L breakdown (today / MTD)
GET  /api/trading/activity/          — recent agent_log entries for the desk
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends

from ..agents.trading_desk_autopilot import (
    run_acquisition_cycle,
    run_coverage_cycle,
    run_daily_close,
    run_settlement_check,
    run_full_cycle,
)
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(prefix="/api/trading", dependencies=[Depends(require_bearer)])

_ESCALATE_MIN = 90  # minutes before a load is considered at-risk


def _minutes_ago(ts_str: str) -> float:
    try:
        ts = datetime.fromisoformat((ts_str or "").replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 60
    except Exception:
        return 0


@router.post("/run-acquisition/")
def api_run_acquisition(states: str = "", per_state: int = 15) -> dict:
    """Trigger Jordan acquisition scan. Optionally pass comma-separated states."""
    state_list = [s.strip().upper() for s in states.split(",") if s.strip()] or None
    return run_acquisition_cycle(states=state_list, per_state=per_state)


@router.post("/run-coverage/")
def api_run_coverage(max_calls: int = 8) -> dict:
    """Trigger Casey coverage sweep + auto-call escalation."""
    return run_coverage_cycle(max_calls=max_calls)


@router.post("/run-settlement/")
def api_run_settlement() -> dict:
    """Auto-settle loads whose delivery date has passed."""
    return run_settlement_check()


@router.post("/run-full/")
def api_run_full() -> dict:
    """Run acquisition + coverage + settlement in one call."""
    return run_full_cycle()


@router.post("/daily-close/")
def api_daily_close() -> dict:
    """Trigger end-of-day P&L close manually."""
    return run_daily_close()


@router.get("/live-book/")
def api_live_book(limit: int = 50) -> dict:
    """All open positions enriched with age, risk level, and coverage status."""
    db = get_supabase()
    rows = (
        db.table("brokered_loads")
        .select("id,origin_city,origin_state,dest_city,dest_state,miles,sell_rate,buy_rate,"
                "gross_margin,margin_pct,pickup_date,delivery_date,status,sourced_by,covered_by,"
                "covering_carrier_name,covering_carrier_mc,source_platform,trailer_type,notes,created_at,updated_at")
        .not_.in_("status", ["settled", "cancelled"])
        .order("pickup_date")
        .limit(limit)
        .execute()
    ).data or []

    enriched = []
    for r in rows:
        age_min  = _minutes_ago(r.get("created_at") or "")
        sell     = float(r.get("sell_rate") or 0)
        buy      = float(r.get("buy_rate")  or 0)
        gm       = sell - buy
        mp       = round(gm / sell * 100, 1) if sell else 0
        status   = r.get("status", "unknown")

        risk = "ok"
        if status == "sourced" and age_min >= _ESCALATE_MIN:
            risk = "at_risk"
        elif status == "sourced" and age_min >= _ESCALATE_MIN / 2:
            risk = "watch"

        enriched.append({
            **r,
            "gross_margin": round(gm, 2),
            "margin_pct":   mp,
            "age_minutes":  round(age_min),
            "risk":         risk,
        })

    uncovered = [r for r in enriched if r["status"] == "sourced"]
    at_risk   = [r for r in uncovered if r["risk"] == "at_risk"]

    return {
        "ok": True,
        "open_positions": len(enriched),
        "uncovered": len(uncovered),
        "at_risk": len(at_risk),
        "loads": enriched,
    }


@router.get("/pnl-summary/")
def api_pnl_summary() -> dict:
    """P&L breakdown — today and MTD."""
    db    = get_supabase()
    today = date.today().isoformat()
    mtd   = date.today().replace(day=1).isoformat()

    def _agg(rows: list[dict]) -> dict[str, Any]:
        settled  = [r for r in rows if r.get("status") == "settled"]
        rev      = sum(float(r.get("sell_rate") or 0) for r in rows)
        cost     = sum(float(r.get("buy_rate")  or 0) for r in rows)
        margin   = sum(float(r.get("gross_margin") or (float(r.get("sell_rate") or 0) - float(r.get("buy_rate") or 0))) for r in rows)
        s_margin = sum(float(r.get("gross_margin") or 0) for r in settled)
        avg_mp   = round(sum(float(r.get("margin_pct") or 0) for r in rows) / len(rows), 1) if rows else 0
        return {
            "loads": len(rows), "settled": len(settled),
            "revenue": round(rev, 2), "cost": round(cost, 2),
            "gross_margin": round(margin, 2), "settled_margin": round(s_margin, 2),
            "avg_margin_pct": avg_mp,
        }

    today_rows = (db.table("brokered_loads").select("sell_rate,buy_rate,gross_margin,margin_pct,status,sourced_by")
                  .gte("created_at", today).execute()).data or []
    mtd_rows   = (db.table("brokered_loads").select("sell_rate,buy_rate,gross_margin,margin_pct,status,sourced_by")
                  .gte("created_at", mtd).execute()).data or []

    # By trader
    traders: dict[str, dict] = {}
    for r in mtd_rows:
        t = r.get("sourced_by") or "unknown"
        if t not in traders:
            traders[t] = {"loads": 0, "revenue": 0.0, "margin": 0.0}
        traders[t]["loads"]   += 1
        traders[t]["revenue"] += float(r.get("sell_rate") or 0)
        traders[t]["margin"]  += float(r.get("gross_margin") or 0)

    return {"ok": True, "today": _agg(today_rows), "mtd": _agg(mtd_rows), "by_trader": traders}


@router.get("/activity/")
def api_activity(limit: int = 40) -> dict:
    """Recent agent_log entries from the trading desk agents."""
    db = get_supabase()
    rows = (
        db.table("agent_log")
        .select("*")
        .in_("agent", ["rex", "jordan", "casey"])
        .order("ts", desc=True)
        .limit(limit)
        .execute()
    ).data or []
    return {"ok": True, "activity": rows}

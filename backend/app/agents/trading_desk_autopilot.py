"""Trading Desk Autopilot — automated load acquisition, coverage, and settlement.

Rex scores every candidate. Jordan sources loads from top freight states every 2 hours.
Casey sweeps for uncovered loads every 30 minutes and auto-calls carriers.
At 5 PM UTC the desk closes and logs the daily P&L.

Exported functions (called from triggers.py + API route):
  run_acquisition_cycle()   — Jordan scans hot states, Rex scores, auto-posts ≥7.5
  run_coverage_cycle()      — Casey sweeps uncovered loads, auto-calls carriers
  run_settlement_check()    — close loads past delivery date
  run_daily_close()         — end-of-day P&L summary → agent_log
  run_full_cycle()          — all four in sequence
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem

log = logging.getLogger("3ll.trading_autopilot")

# ── Config ────────────────────────────────────────────────────────────────────

# States Jordan auto-scans every cycle (highest-volume freight lanes in North America)
_HOT_ORIGIN_STATES = ["TX", "OH", "GA", "IL", "CA", "FL", "TN", "PA", "NC", "MO"]

# Auto-post threshold: Rex score ≥ this → post without human review
_AUTO_POST_SCORE = 7.5

# Coverage escalation: loads uncovered longer than this → priority Bland AI call
_ESCALATE_AFTER_MINUTES = 90

# Max auto-calls per coverage cycle (rate limit)
_MAX_AUTO_CALLS = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minutes_ago(ts_str: str) -> float:
    """Return how many minutes ago an ISO timestamp was."""
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 60
    except Exception:
        return 0


# ── Acquisition Cycle ─────────────────────────────────────────────────────────

def run_acquisition_cycle(states: list[str] | None = None, per_state: int = 15) -> dict[str, Any]:
    """Jordan scans hot origin states; Rex scores every candidate; auto-posts ≥7.5."""
    from .jordan import source_loads
    from .rex import score_load

    target_states = states or _HOT_ORIGIN_STATES
    posted = 0
    skipped = 0
    errors = 0
    top_margins: list[float] = []

    for state in target_states:
        try:
            result = source_loads({
                "origin_state": state,
                "trailer_type": "dry_van",
                "min_rate_per_mile": 2.10,
                "min_margin_pct": 10.0,
            })
            candidates = (result.get("top_loads") or [])[:per_state]

            for load in candidates:
                sell = float(load.get("sell_rate") or 0)
                buy  = float(load.get("implied_buy_rate") or sell * 0.82)
                miles = int(load.get("miles") or 0)

                scored = score_load({
                    "sell_rate":    sell,
                    "buy_rate":     buy,
                    "miles":        miles,
                    "origin_state": load.get("origin_state", state),
                    "dest_state":   load.get("dest_state", ""),
                    "origin_city":  load.get("origin_city", ""),
                    "dest_city":    load.get("dest_city", ""),
                    "commodity":    load.get("commodity"),
                    "trailer_type": load.get("trailer_type", "dry_van"),
                    "pickup_date":  load.get("pickup_date"),
                })

                rec = scored.get("recommendation", "pass")
                score = float(scored.get("score") or 0)

                if score >= _AUTO_POST_SCORE and rec in ("book", "negotiate"):
                    # Auto-post via Jordan
                    from .jordan import post_load
                    post_result = post_load({
                        "origin_city":    load.get("origin_city", ""),
                        "origin_state":   load.get("origin_state", state),
                        "dest_city":      load.get("dest_city", ""),
                        "dest_state":     load.get("dest_state", ""),
                        "miles":          miles,
                        "sell_rate":      sell,
                        "buy_rate":       buy,
                        "pickup_date":    load.get("pickup_date"),
                        "source_platform": load.get("source", "dat"),
                        "source_load_id": load.get("load_id"),
                        "notes": f"Auto-posted by autopilot. Rex score={score:.1f} rec={rec}. {scored.get('rationale','')}",
                    })
                    if post_result.get("status") == "posted":
                        posted += 1
                        margin = sell - buy
                        top_margins.append(margin)
                else:
                    skipped += 1
        except Exception as exc:
            log.warning("Acquisition error for %s: %s", state, exc)
            errors += 1

    avg_margin = round(sum(top_margins) / len(top_margins), 2) if top_margins else 0
    summary = f"acquisition: posted={posted} skipped={skipped} errors={errors} avg_margin=${avg_margin:.0f}"
    log_agent("rex", "auto_acquisition", payload={"states": target_states}, result=summary)
    mem.remember("rex", "last_acquisition", {"posted": posted, "avg_margin": avg_margin, "states": target_states},
                 summary=summary)

    return {
        "ok": True,
        "cycle": "acquisition",
        "states_scanned": len(target_states),
        "posted": posted,
        "skipped_low_score": skipped,
        "errors": errors,
        "avg_margin_posted": avg_margin,
        "top_margins": sorted(top_margins, reverse=True)[:5],
    }


# ── Coverage Cycle ────────────────────────────────────────────────────────────

def run_coverage_cycle(max_calls: int = _MAX_AUTO_CALLS) -> dict[str, Any]:
    """Casey sweeps for uncovered loads, auto-calls carriers for priority loads."""
    from .casey import find_coverage, call_carrier

    db = get_supabase()
    now = _now_iso()

    uncovered = (
        db.table("brokered_loads")
        .select("id,origin_city,origin_state,dest_city,dest_state,miles,sell_rate,buy_rate,pickup_date,status,created_at,trailer_type")
        .eq("status", "sourced")
        .order("created_at")
        .limit(30)
        .execute()
    ).data or []

    calls_made = 0
    strategies_built = 0
    escalated = 0

    for load in uncovered:
        if calls_made >= max_calls:
            break

        age_min = _minutes_ago(load.get("created_at") or now)
        sell = float(load.get("sell_rate") or 0)
        buy  = float(load.get("buy_rate") or sell * 0.82)
        miles = int(load.get("miles") or 0)

        # Get coverage strategy
        try:
            strategy_result = find_coverage({
                "load_id":      load["id"],
                "origin_state": load.get("origin_state", ""),
                "dest_state":   load.get("dest_state", ""),
                "miles":        miles,
                "sell_rate":    sell,
                "target_buy_rate": buy,
                "pickup_date":  load.get("pickup_date"),
                "trailer_type": load.get("trailer_type", "dry_van"),
            })
            strategies_built += 1

            # For loads sitting uncovered past threshold → auto-call top carrier
            if age_min >= _ESCALATE_AFTER_MINUTES:
                escalated += 1
                # Try DB carriers first
                db_carriers = strategy_result.get("top_db_carriers") or []
                call_target = next((c for c in db_carriers if c.get("phone")), None)

                if call_target:
                    call_result = call_carrier({
                        "phone":        call_target["phone"],
                        "carrier_name": call_target.get("company_name") or call_target.get("mc_number", "Carrier"),
                        "load_id":      load["id"],
                        "origin_state": load.get("origin_state"),
                        "dest_state":   load.get("dest_state"),
                        "buy_rate":     buy,
                        "miles":        miles,
                        "pickup_date":  load.get("pickup_date"),
                    })
                    if call_result.get("call_result", {}).get("status") in ("started", "queued"):
                        calls_made += 1

                # Log the escalation
                log_agent("casey", "auto_coverage_escalation",
                          payload={"load_id": load["id"], "age_min": round(age_min)},
                          result=f"called={bool(call_target)} age={age_min:.0f}min")

        except Exception as exc:
            log.warning("Coverage cycle error for load %s: %s", load.get("id"), exc)

    summary = f"coverage: uncovered={len(uncovered)} strategies={strategies_built} escalated={escalated} calls={calls_made}"
    log_agent("casey", "auto_coverage_sweep", payload={"uncovered": len(uncovered)}, result=summary)
    mem.remember("casey", "last_coverage_sweep",
                 {"uncovered": len(uncovered), "calls_made": calls_made, "escalated": escalated},
                 summary=summary)

    return {
        "ok": True,
        "cycle": "coverage",
        "uncovered_loads": len(uncovered),
        "strategies_built": strategies_built,
        "escalated": escalated,
        "calls_made": calls_made,
    }


# ── Settlement Check ──────────────────────────────────────────────────────────

def run_settlement_check() -> dict[str, Any]:
    """Auto-settle loads whose delivery date has passed and status is 'covered' or 'dispatched'."""
    db = get_supabase()
    today = date.today().isoformat()

    overdue = (
        db.table("brokered_loads")
        .select("id,sell_rate,buy_rate,origin_state,dest_state,delivery_date,status")
        .in_("status", ["covered", "dispatched"])
        .lte("delivery_date", today)
        .limit(50)
        .execute()
    ).data or []

    settled = 0
    for load in overdue:
        try:
            sell = float(load.get("sell_rate") or 0)
            buy  = float(load.get("buy_rate")  or 0)
            gm   = sell - buy
            mp   = round(gm / sell * 100, 2) if sell else 0
            db.table("brokered_loads").update({
                "status": "settled",
                "settled_at": _now_iso(),
                "gross_margin": round(gm, 2),
                "margin_pct": mp,
            }).eq("id", load["id"]).execute()
            settled += 1
        except Exception as exc:
            log.warning("Settlement error for %s: %s", load.get("id"), exc)

    log_agent("rex", "auto_settlement", payload={"overdue": len(overdue)}, result=f"settled={settled}")
    return {"ok": True, "cycle": "settlement", "auto_settled": settled}


# ── Daily Close ───────────────────────────────────────────────────────────────

def run_daily_close() -> dict[str, Any]:
    """End-of-day P&L roll-up — called at 5 PM UTC."""
    from .rex import daily_pnl
    pnl = daily_pnl({})

    msg = (
        f"📈 Trading Desk Daily Close — {date.today().isoformat()}\n"
        f"Loads: {pnl['total_loads']} total, {pnl['settled_loads']} settled\n"
        f"Revenue: ${pnl['gross_revenue']:,.0f}  Cost: ${pnl['carrier_cost']:,.0f}  "
        f"Margin: ${pnl['gross_margin']:,.0f} ({pnl['avg_margin_pct']:.1f}%)"
    )
    log_agent("rex", "daily_close", payload={}, result=msg)
    mem.remember("rex", "daily_close", pnl, summary=msg)
    log.info(msg)
    return {"ok": True, "cycle": "daily_close", **pnl}


# ── Full Cycle ────────────────────────────────────────────────────────────────

def run_full_cycle(payload: dict | None = None) -> dict[str, Any]:
    """Run acquisition + coverage + settlement in sequence."""
    p = payload or {}
    acq  = run_acquisition_cycle(states=p.get("states"), per_state=p.get("per_state", 15))
    cov  = run_coverage_cycle(max_calls=p.get("max_calls", _MAX_AUTO_CALLS))
    sett = run_settlement_check()
    return {"ok": True, "acquisition": acq, "coverage": cov, "settlement": sett}


def run(payload: dict | None = None) -> dict[str, Any]:
    return run_full_cycle(payload)

"""Rex Morgan — Senior Desk Trader & Book Manager.

12 years on freight trading desks (TQL, Coyote) before joining 3 Lakes.
Rex owns the trading book: he scores every load opportunity, tracks open
positions, monitors P&L, and directs Jordan and Casey on which lanes to
chase and what spreads to target.

Actions via run(payload):
  score_load    — Claude-powered lane/margin scoring for a candidate load
  book_status   — open positions, today's P&L, risk summary
  daily_pnl     — full P&L breakdown by trader and lane
  close_position — mark a brokered load settled, record final margin
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import memory as mem

_SYSTEM = """You are Rex Morgan, Senior Desk Trader at 3 Lakes Logistics freight brokerage.

You evaluate load opportunities with the cold precision of a trading desk. Given lane data,
market rates, and margin figures, you score each load 0-10 and give a one-line rationale.

Scoring rubric:
  9-10  Premium opportunity — margin >20%, lane has strong carrier availability, low deadhead
  7-8   Good trade — margin 15-20%, standard lane, manageable coverage risk
  5-6   Marginal — margin 10-15% or tight timeline, proceed with caution
  3-4   Risky — thin margin <10% or difficult lane/commodity
  0-2   Pass — margin negative, extremely tight timeline, or problem commodity

Always return valid JSON only:
{
  "score": 7.5,
  "recommendation": "book" | "pass" | "negotiate",
  "rationale": "one clear sentence",
  "target_buy_rate": 1850.00,
  "risk_flags": ["list", "of", "flags"]
}"""


def _call_claude(load_data: dict) -> dict | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": s.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 400,
                "system": _SYSTEM,
                "messages": [{"role": "user", "content": f"Score this load opportunity:\n\n{json.dumps(load_data, default=str)}"}],
            },
            timeout=20,
        )
        if r.status_code == 200:
            text = r.json()["content"][0]["text"].strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
    except Exception:
        pass
    return None


def _rule_score(sell_rate: float, buy_rate: float, miles: int) -> dict:
    """Fallback scoring when Claude is unavailable."""
    if not sell_rate or not buy_rate:
        return {"score": 0, "recommendation": "pass", "rationale": "Missing rate data", "risk_flags": ["no_rates"]}
    margin = sell_rate - buy_rate
    margin_pct = (margin / sell_rate * 100) if sell_rate else 0
    rpm_sell = sell_rate / miles if miles else 0
    rpm_buy = buy_rate / miles if miles else 0

    if margin_pct >= 20:
        score, rec = 8.5, "book"
    elif margin_pct >= 15:
        score, rec = 7.0, "book"
    elif margin_pct >= 10:
        score, rec = 5.5, "negotiate"
    elif margin_pct >= 5:
        score, rec = 3.5, "negotiate"
    else:
        score, rec = 1.5, "pass"

    flags = []
    if rpm_sell < 2.0:
        flags.append("low_sell_rpm")
    if rpm_buy < 1.5:
        flags.append("suspiciously_low_buy")
    if margin < 150:
        flags.append("thin_abs_margin")

    return {
        "score": score,
        "recommendation": rec,
        "rationale": f"${margin:.0f} margin ({margin_pct:.1f}%) on {miles or '?'} miles — sell ${rpm_sell:.2f}/mi buy ${rpm_buy:.2f}/mi",
        "target_buy_rate": round(sell_rate * 0.82, 2),
        "risk_flags": flags,
    }


def score_load(payload: dict) -> dict:
    sell_rate = float(payload.get("sell_rate") or 0)
    buy_rate  = float(payload.get("buy_rate")  or 0)
    miles     = int(payload.get("miles")        or 0)
    origin    = f"{payload.get('origin_city','')}, {payload.get('origin_state','')}"
    dest      = f"{payload.get('dest_city','')}, {payload.get('dest_state','')}"

    load_data = {
        "lane": f"{origin} → {dest}",
        "miles": miles,
        "sell_rate": sell_rate,
        "buy_rate": buy_rate,
        "margin": sell_rate - buy_rate,
        "margin_pct": round((sell_rate - buy_rate) / sell_rate * 100, 1) if sell_rate else 0,
        "sell_rpm": round(sell_rate / miles, 2) if miles else None,
        "buy_rpm": round(buy_rate / miles, 2) if miles else None,
        "commodity": payload.get("commodity"),
        "trailer_type": payload.get("trailer_type", "dry_van"),
        "pickup_date": payload.get("pickup_date"),
        "weight_lbs": payload.get("weight_lbs"),
    }

    intel = _call_claude(load_data) or _rule_score(sell_rate, buy_rate, miles)
    intel["load_data"] = load_data

    log_agent("rex", "score_load", payload=payload, result=f"score={intel.get('score')} rec={intel.get('recommendation')}")
    return {"agent": "rex", "action": "score_load", **intel}


def book_status(payload: dict) -> dict:
    db = get_supabase()
    open_rows = (
        db.table("brokered_loads")
        .select("id,origin_state,dest_state,miles,sell_rate,buy_rate,gross_margin,status,sourced_by,covered_by,pickup_date")
        .not_.in_("status", ["settled", "cancelled"])
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    ).data or []

    today = date.today().isoformat()
    today_settled = (
        db.table("brokered_loads")
        .select("gross_margin,sell_rate,buy_rate,sourced_by")
        .eq("status", "settled")
        .gte("settled_at", today)
        .execute()
    ).data or []

    total_margin_today = sum(float(r.get("gross_margin") or 0) for r in today_settled)
    total_revenue_today = sum(float(r.get("sell_rate") or 0) for r in today_settled)

    by_status: dict[str, int] = {}
    at_risk: list[dict] = []
    for r in open_rows:
        s = r.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
        if s in ("sourced",) and not r.get("covered_by"):
            at_risk.append({"id": r["id"], "lane": f"{r.get('origin_state')}→{r.get('dest_state')}", "pickup": r.get("pickup_date")})

    log_agent("rex", "book_status", result=f"open={len(open_rows)} today_margin=${total_margin_today:.0f}")
    return {
        "agent": "rex",
        "action": "book_status",
        "open_positions": len(open_rows),
        "by_status": by_status,
        "uncovered_loads": len(at_risk),
        "at_risk": at_risk[:10],
        "today_settled": len(today_settled),
        "today_gross_revenue": round(total_revenue_today, 2),
        "today_gross_margin": round(total_margin_today, 2),
    }


def daily_pnl(payload: dict) -> dict:
    db = get_supabase()
    since = payload.get("since") or date.today().replace(day=1).isoformat()
    rows = (
        db.table("brokered_loads")
        .select("id,gross_margin,sell_rate,buy_rate,margin_pct,status,sourced_by,covered_by,origin_state,dest_state,settled_at,created_at")
        .gte("created_at", since)
        .execute()
    ).data or []

    total_rev   = sum(float(r.get("sell_rate") or 0)     for r in rows)
    total_cost  = sum(float(r.get("buy_rate") or 0)      for r in rows)
    total_margin = sum(float(r.get("gross_margin") or 0) for r in rows)
    settled     = [r for r in rows if r.get("status") == "settled"]
    settled_margin = sum(float(r.get("gross_margin") or 0) for r in settled)

    by_trader: dict[str, dict] = {}
    for r in rows:
        t = r.get("sourced_by") or "unknown"
        if t not in by_trader:
            by_trader[t] = {"loads": 0, "revenue": 0.0, "margin": 0.0}
        by_trader[t]["loads"]   += 1
        by_trader[t]["revenue"] += float(r.get("sell_rate") or 0)
        by_trader[t]["margin"]  += float(r.get("gross_margin") or 0)

    log_agent("rex", "daily_pnl", result=f"loads={len(rows)} margin=${total_margin:.0f}")
    return {
        "agent": "rex",
        "action": "daily_pnl",
        "since": since,
        "total_loads": len(rows),
        "settled_loads": len(settled),
        "gross_revenue": round(total_rev, 2),
        "carrier_cost": round(total_cost, 2),
        "gross_margin": round(total_margin, 2),
        "settled_margin": round(settled_margin, 2),
        "avg_margin_pct": round(sum(float(r.get("margin_pct") or 0) for r in rows) / len(rows), 1) if rows else 0,
        "by_trader": by_trader,
    }


def close_position(payload: dict) -> dict:
    load_id    = payload.get("load_id") or payload.get("id")
    sell_rate  = payload.get("sell_rate")
    buy_rate   = payload.get("buy_rate")
    if not load_id:
        return {"agent": "rex", "status": "error", "error": "load_id required"}

    update: dict[str, Any] = {
        "status": "settled",
        "settled_at": datetime.now(timezone.utc).isoformat(),
    }
    if sell_rate is not None:
        update["sell_rate"] = float(sell_rate)
    if buy_rate is not None:
        update["buy_rate"] = float(buy_rate)
    if sell_rate and buy_rate:
        margin_pct = round((float(sell_rate) - float(buy_rate)) / float(sell_rate) * 100, 2)
        update["margin_pct"] = margin_pct

    get_supabase().table("brokered_loads").update(update).eq("id", load_id).execute()
    log_agent("rex", "close_position", payload={"load_id": load_id}, result="settled")
    return {"agent": "rex", "action": "close_position", "status": "settled", "load_id": load_id}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "score_load")
    if action == "score_load":
        return score_load(payload)
    if action == "book_status":
        return book_status(payload)
    if action == "daily_pnl":
        return daily_pnl(payload)
    if action == "close_position":
        return close_position(payload)
    return {"agent": "rex", "status": "error", "error": f"unknown action: {action}",
            "valid_actions": ["score_load", "book_status", "daily_pnl", "close_position"]}

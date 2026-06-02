"""Jordan Cross — Load Acquisition Trader.

6 years at Echo Global sourcing spot freight before joining 3 Lakes.
Jordan works the buy side of the book: she finds loads on DAT, Truckstop,
and direct shipper relationships, evaluates lane margins, and posts
confirmed positions into the brokered_loads table for Casey to cover.

She doesn't just search load boards — she reads the market. If a lane is
flooded with loads and short on trucks, she books aggressively. If carriers
are in the driver's seat, she walks away or negotiates harder sell rates.

Actions via run(payload):
  source_loads    — scan load boards for brokerage candidates above margin floor
  post_load       — record an accepted load into brokered_loads
  evaluate_lane   — quick lane analysis (rates, demand signal, coverage outlook)
  open_positions  — loads Jordan has sourced that still need coverage
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from ..prospecting.loadboard_clients import SearchParams, search_all
from . import memory as mem

# Platforms Jordan watches for brokerage opportunities
_BROKER_SOURCES = ["dat", "truckstop", "123loadboard", "cargo_chief", "loadsmart"]

# Minimum gross margin Jordan will consider posting
_MIN_MARGIN_PCT = 12.0

_LANE_SYSTEM = """You are Jordan Cross, Load Acquisition Trader at 3 Lakes Logistics.

Given a lane (origin, destination, miles) and current market rate data, deliver a rapid
lane analysis that tells the desk whether to chase this load, how hard to negotiate
the sell rate, and what coverage risk looks like.

Return valid JSON only:
{
  "demand_signal": "hot" | "normal" | "soft",
  "coverage_outlook": "easy" | "moderate" | "tight",
  "recommended_sell_rate": 2250.00,
  "floor_sell_rate": 2000.00,
  "rationale": "one clear sentence",
  "chase": true
}"""


def _call_claude(lane_data: dict) -> dict | None:
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
                "max_tokens": 300,
                "system": _LANE_SYSTEM,
                "messages": [{"role": "user", "content": f"Analyze this lane:\n\n{json.dumps(lane_data, default=str)}"}],
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


def source_loads(payload: dict) -> dict:
    """Scan load boards for brokerage candidates above the margin floor."""
    origin_state = payload.get("origin_state", "")
    trailer_type = payload.get("trailer_type", "dry_van")
    min_margin_pct = float(payload.get("min_margin_pct") or _MIN_MARGIN_PCT)
    min_rpm = float(payload.get("min_rate_per_mile") or 2.20)

    if not origin_state:
        return {"agent": "jordan", "status": "error", "error": "origin_state required"}

    params = SearchParams(
        origin_state=origin_state,
        trailer_type=trailer_type,
        max_weight_lbs=int(payload.get("max_weight_lbs") or 45000),
        max_deadhead_mi=int(payload.get("max_deadhead_mi") or 200),
        min_rate_per_mile=min_rpm,
        hos_hours_remaining=11.0,
    )

    raw_loads = search_all(params)
    candidates = []
    for load in raw_loads:
        l = load.__dict__ if hasattr(load, "__dict__") else load
        rate   = float(l.get("rate") or l.get("rate_usd") or 0)
        miles  = int(l.get("miles") or l.get("distance_miles") or 0)
        if not rate or not miles:
            continue
        # Jordan targets 18% margin — assumes buy rate ~82% of sell
        implied_buy  = rate * 0.82
        implied_margin_pct = 18.0
        rpm = rate / miles

        if rpm >= min_rpm and implied_margin_pct >= min_margin_pct:
            candidates.append({
                "source": l.get("source", "unknown"),
                "load_id": l.get("load_id") or l.get("id"),
                "origin_city": l.get("origin_city", ""),
                "origin_state": l.get("origin_state", origin_state),
                "dest_city": l.get("dest_city", ""),
                "dest_state": l.get("dest_state", ""),
                "miles": miles,
                "rate_per_mile": round(rpm, 2),
                "sell_rate": rate,
                "implied_buy_rate": round(implied_buy, 2),
                "implied_margin": round(rate - implied_buy, 2),
                "implied_margin_pct": implied_margin_pct,
                "trailer_type": l.get("trailer_type", trailer_type),
                "weight_lbs": l.get("weight_lbs"),
                "pickup_date": l.get("pickup_date") or l.get("available_date"),
            })

    # Sort by implied margin descending
    candidates.sort(key=lambda x: x["implied_margin"], reverse=True)
    top = candidates[:20]

    # Remember best lane intel for future scoring
    if top:
        mem.remember(
            "jordan", "top_lanes",
            {"origin_state": origin_state, "top_loads": top[:5], "scanned_at": datetime.now(timezone.utc).isoformat()},
            confidence=0.7,
            summary=f"{len(top)} candidates from {origin_state} — best margin ${top[0]['implied_margin']:.0f}",
        )

    log_agent("jordan", "source_loads", payload=payload, result=f"{len(candidates)} candidates, showing top {len(top)}")
    return {
        "agent": "jordan",
        "action": "source_loads",
        "origin_state": origin_state,
        "candidates_found": len(candidates),
        "top_loads": top,
        "sources_queried": _BROKER_SOURCES,
    }


def post_load(payload: dict) -> dict:
    """Record an accepted load into brokered_loads and score it via Rex."""
    required = ["origin_city", "origin_state", "dest_city", "dest_state", "sell_rate"]
    missing = [f for f in required if not payload.get(f)]
    if missing:
        return {"agent": "jordan", "status": "error", "error": f"missing fields: {missing}"}

    sell_rate = float(payload["sell_rate"])
    buy_rate  = float(payload.get("buy_rate") or sell_rate * 0.82)
    miles     = int(payload.get("miles") or 0)
    margin_pct = round((sell_rate - buy_rate) / sell_rate * 100, 2) if sell_rate else 0

    row = {
        "origin_city":    payload["origin_city"],
        "origin_state":   payload["origin_state"].upper()[:2],
        "dest_city":      payload["dest_city"],
        "dest_state":     payload["dest_state"].upper()[:2],
        "miles":          miles or None,
        "weight_lbs":     payload.get("weight_lbs"),
        "commodity":      payload.get("commodity"),
        "trailer_type":   payload.get("trailer_type", "dry_van"),
        "pickup_date":    payload.get("pickup_date"),
        "delivery_date":  payload.get("delivery_date"),
        "source_platform": payload.get("source_platform", "direct"),
        "source_load_id": payload.get("source_load_id"),
        "shipper_name":   payload.get("shipper_name"),
        "broker_name":    payload.get("broker_name"),
        "sell_rate":      sell_rate,
        "buy_rate":       buy_rate,
        "margin_pct":     margin_pct,
        "status":         "sourced",
        "sourced_by":     "jordan",
        "notes":          payload.get("notes"),
    }

    result = get_supabase().table("brokered_loads").insert(row).execute()
    load_id = (result.data or [{}])[0].get("id") if result.data else None

    log_agent("jordan", "post_load", payload={"lane": f"{row['origin_state']}→{row['dest_state']}", "sell_rate": sell_rate},
              result=f"posted id={load_id} margin={margin_pct:.1f}%")

    return {
        "agent": "jordan",
        "action": "post_load",
        "status": "posted",
        "load_id": load_id,
        "lane": f"{payload['origin_city']}, {payload['origin_state']} → {payload['dest_city']}, {payload['dest_state']}",
        "sell_rate": sell_rate,
        "buy_rate": buy_rate,
        "gross_margin": round(sell_rate - buy_rate, 2),
        "margin_pct": margin_pct,
    }


def evaluate_lane(payload: dict) -> dict:
    """Quick lane analysis — demand signal, coverage outlook, rate target."""
    origin_state = payload.get("origin_state", "")
    dest_state   = payload.get("dest_state", "")
    miles        = payload.get("miles")
    market_rate  = payload.get("market_rate")
    target_rate  = payload.get("target_sell_rate") or market_rate

    lane_data = {
        "origin_state": origin_state,
        "dest_state": dest_state,
        "miles": miles,
        "market_rate": market_rate,
        "target_sell_rate": target_rate,
        "trailer_type": payload.get("trailer_type", "dry_van"),
        "pickup_date": payload.get("pickup_date"),
        "commodity": payload.get("commodity"),
    }

    intel = _call_claude(lane_data)
    if not intel:
        rpm = float(target_rate) / int(miles) if target_rate and miles else 0
        intel = {
            "demand_signal": "normal",
            "coverage_outlook": "moderate",
            "recommended_sell_rate": target_rate,
            "floor_sell_rate": float(target_rate) * 0.92 if target_rate else None,
            "rationale": f"${rpm:.2f}/mi — standard lane analysis",
            "chase": rpm >= 2.10,
        }

    log_agent("jordan", "evaluate_lane", payload=payload, result=f"signal={intel.get('demand_signal')} chase={intel.get('chase')}")
    return {"agent": "jordan", "action": "evaluate_lane", "lane": f"{origin_state}→{dest_state}", **intel}


def open_positions(payload: dict) -> dict:
    """Loads Jordan sourced that still need carrier coverage."""
    rows = (
        get_supabase()
        .table("brokered_loads")
        .select("id,origin_city,origin_state,dest_city,dest_state,miles,sell_rate,buy_rate,gross_margin,pickup_date,status,covering_carrier_name")
        .eq("sourced_by", "jordan")
        .not_.in_("status", ["settled", "cancelled"])
        .order("pickup_date")
        .limit(30)
        .execute()
    ).data or []

    uncovered = [r for r in rows if r.get("status") == "sourced"]
    log_agent("jordan", "open_positions", result=f"open={len(rows)} uncovered={len(uncovered)}")
    return {
        "agent": "jordan",
        "action": "open_positions",
        "open_loads": len(rows),
        "uncovered_loads": len(uncovered),
        "positions": rows,
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "source_loads")
    if action == "source_loads":
        return source_loads(payload)
    if action == "post_load":
        return post_load(payload)
    if action == "evaluate_lane":
        return evaluate_lane(payload)
    if action == "open_positions":
        return open_positions(payload)
    return {"agent": "jordan", "status": "error", "error": f"unknown action: {action}",
            "valid_actions": ["source_loads", "post_load", "evaluate_lane", "open_positions"]}

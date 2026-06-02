"""Casey Lane — Carrier Coverage Trader.

5 years at XPO covering spot loads before 3 Lakes. Casey works the sell
side of the book: once Jordan posts a load, Casey finds a carrier, negotiates
the buy rate, and locks in coverage. Her carrier network is her edge.

She uses Bland AI (via the Vance client) to call carriers directly, and
posts to load boards when the phone doesn't move fast enough. She never
lets a load sit uncovered past 4 hours without escalating to Rex.

Actions via run(payload):
  find_coverage    — search load boards + carrier DB for trucks on a specific load
  call_carrier     — trigger Bland AI outbound call to a carrier about a load
  confirm_coverage — lock in a carrier, set buy rate, update brokered_loads
  covered_today    — summary of loads Casey has covered today
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
from .bland_client import start_outbound_call
from . import memory as mem

_COVERAGE_SYSTEM = """You are Casey Lane, Carrier Coverage Trader at 3 Lakes Logistics.

Given a load that needs coverage and carrier options available, decide which carrier
to approach first, what buy rate to offer, and how to frame the call.

Return valid JSON only:
{
  "top_carrier": "carrier name or MC#",
  "opening_buy_rate": 1850.00,
  "walk_away_buy_rate": 2050.00,
  "call_script_hint": "two sentences: hook + rate",
  "backup_strategy": "post to DAT at $X or call [carrier name]"
}"""


def _call_claude(load_data: dict, carriers: list[dict]) -> dict | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    try:
        context = {"load": load_data, "available_carriers": carriers[:5]}
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": s.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 350,
                "system": _COVERAGE_SYSTEM,
                "messages": [{"role": "user", "content": f"Coverage strategy for this load:\n\n{json.dumps(context, default=str)}"}],
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


def find_coverage(payload: dict) -> dict:
    """Find carriers to cover an open brokered load."""
    load_id      = payload.get("load_id")
    origin_state = payload.get("origin_state", "")
    dest_state   = payload.get("dest_state", "")
    sell_rate    = float(payload.get("sell_rate") or 0)
    miles        = int(payload.get("miles") or 0)
    trailer_type = payload.get("trailer_type", "dry_van")
    target_buy   = float(payload.get("target_buy_rate") or sell_rate * 0.82)

    if not origin_state:
        return {"agent": "casey", "status": "error", "error": "origin_state required"}

    # 1. Search carrier database for trucks near origin
    db = get_supabase()
    db_carriers = (
        db.table("active_carriers")
        .select("id,company_name,mc_number,phone,trailer_types,home_state")
        .eq("status", "active")
        .execute()
    ).data or []

    # Filter for carriers near origin or in matching home state
    nearby = [
        c for c in db_carriers
        if (c.get("home_state") or "").upper() == origin_state.upper()
    ]

    # 2. Search load boards for available trucks on this lane
    params = SearchParams(
        origin_state=dest_state,  # trucks returning from destination
        trailer_type=trailer_type,
        max_weight_lbs=45000,
        max_deadhead_mi=300,
        min_rate_per_mile=target_buy / miles if miles else 1.80,
        hos_hours_remaining=11.0,
    )
    board_trucks = []
    try:
        raw = search_all(params)
        for t in raw[:10]:
            l = t.__dict__ if hasattr(t, "__dict__") else t
            board_trucks.append({
                "source": l.get("source", "load_board"),
                "carrier": l.get("carrier_name") or l.get("company"),
                "mc": l.get("mc_number") or l.get("mc"),
                "phone": l.get("phone"),
                "origin": f"{l.get('origin_city','')}, {l.get('origin_state','')}",
            })
    except Exception:
        pass

    load_data = {
        "load_id": load_id,
        "lane": f"{origin_state} → {dest_state}",
        "miles": miles,
        "sell_rate": sell_rate,
        "target_buy_rate": round(target_buy, 2),
        "trailer_type": trailer_type,
        "pickup_date": payload.get("pickup_date"),
    }

    strategy = _call_claude(load_data, nearby[:5] + board_trucks[:5])
    if not strategy:
        rpm_buy = target_buy / miles if miles else 0
        strategy = {
            "opening_buy_rate": round(target_buy, 2),
            "walk_away_buy_rate": round(sell_rate * 0.90, 2),
            "call_script_hint": f"Got a {origin_state}→{dest_state} load, {miles} miles, picking up soon. Paying ${target_buy:.0f} — you available?",
            "backup_strategy": f"Post to DAT at ${target_buy:.0f} (${rpm_buy:.2f}/mi) if no answer in 2 hours",
        }

    log_agent("casey", "find_coverage", payload=payload,
              result=f"db_carriers={len(nearby)} board_trucks={len(board_trucks)}")
    return {
        "agent": "casey",
        "action": "find_coverage",
        "load_id": load_id,
        "db_carriers_nearby": len(nearby),
        "board_trucks_available": len(board_trucks),
        "top_db_carriers": nearby[:5],
        "strategy": strategy,
    }


def call_carrier(payload: dict) -> dict:
    """Trigger Bland AI outbound call to a carrier about a specific load."""
    phone        = payload.get("phone", "")
    carrier_name = payload.get("carrier_name") or payload.get("company_name") or "Carrier"
    load_id      = payload.get("load_id", "")
    origin_state = payload.get("origin_state", "")
    dest_state   = payload.get("dest_state", "")
    buy_rate     = payload.get("buy_rate") or payload.get("target_buy_rate")
    miles        = payload.get("miles")
    pickup_date  = payload.get("pickup_date", "")

    if not phone:
        return {"agent": "casey", "status": "error", "error": "phone required"}

    script = (
        f"Hey, this is Casey from 3 Lakes Logistics. I've got a load "
        f"{origin_state} to {dest_state}, {miles or '?'} miles, "
        f"picking up {pickup_date or 'today'}. Paying ${buy_rate or 'competitive rate'}. "
        f"You available to cover?"
    )

    result = start_outbound_call(
        lead_id=load_id or "coverage",
        phone=phone,
        prospect_name=carrier_name,
        prospect_email="",
        company_name=carrier_name,
        dot_number="",
        current_pain=f"coverage call for load {origin_state}→{dest_state}",
        webhook_url="",
    )

    log_agent("casey", "call_carrier", payload={"phone": phone, "load_id": load_id},
              result=result.get("status", "unknown"))
    return {
        "agent": "casey",
        "action": "call_carrier",
        "phone": phone,
        "carrier": carrier_name,
        "load_id": load_id,
        "call_result": result,
        "script_used": script,
    }


def confirm_coverage(payload: dict) -> dict:
    """Lock in a carrier for a brokered load — update brokered_loads and advance status."""
    load_id       = payload.get("load_id")
    buy_rate      = payload.get("buy_rate")
    carrier_name  = payload.get("carrier_name") or payload.get("company_name")
    carrier_mc    = payload.get("mc_number") or payload.get("carrier_mc")
    carrier_id    = payload.get("carrier_id")
    driver_phone  = payload.get("driver_phone")

    if not load_id:
        return {"agent": "casey", "status": "error", "error": "load_id required"}
    if not buy_rate:
        return {"agent": "casey", "status": "error", "error": "buy_rate required to confirm coverage"}

    buy_rate = float(buy_rate)
    db = get_supabase()

    # Fetch current load to recalculate margin
    existing = (db.table("brokered_loads").select("sell_rate").eq("id", load_id).single().execute()).data or {}
    sell_rate = float(existing.get("sell_rate") or 0)
    margin_pct = round((sell_rate - buy_rate) / sell_rate * 100, 2) if sell_rate else 0

    update = {
        "status": "covered",
        "covered_by": "casey",
        "buy_rate": buy_rate,
        "margin_pct": margin_pct,
        "covering_carrier_name": carrier_name,
        "covering_carrier_mc": carrier_mc,
        "covering_carrier_id": str(carrier_id) if carrier_id else None,
        "covering_driver_phone": driver_phone,
    }
    db.table("brokered_loads").update(update).eq("id", load_id).execute()

    mem.remember(
        "casey", f"coverage_{load_id}",
        {"carrier": carrier_name, "buy_rate": buy_rate, "margin_pct": margin_pct},
        confidence=0.95,
        summary=f"Covered load {load_id} with {carrier_name} at ${buy_rate:.0f} ({margin_pct:.1f}% margin)",
    )

    log_agent("casey", "confirm_coverage", payload={"load_id": load_id, "carrier": carrier_name},
              result=f"covered at ${buy_rate:.0f} margin={margin_pct:.1f}%")
    return {
        "agent": "casey",
        "action": "confirm_coverage",
        "status": "covered",
        "load_id": load_id,
        "carrier": carrier_name,
        "buy_rate": buy_rate,
        "sell_rate": sell_rate,
        "gross_margin": round(sell_rate - buy_rate, 2),
        "margin_pct": margin_pct,
    }


def covered_today(payload: dict) -> dict:
    """All loads Casey has covered today."""
    today = date.today().isoformat()
    rows = (
        get_supabase()
        .table("brokered_loads")
        .select("id,origin_state,dest_state,miles,sell_rate,buy_rate,gross_margin,margin_pct,covering_carrier_name,status,updated_at")
        .eq("covered_by", "casey")
        .gte("updated_at", today)
        .execute()
    ).data or []

    total_margin = sum(float(r.get("gross_margin") or 0) for r in rows)
    log_agent("casey", "covered_today", result=f"covered={len(rows)} margin=${total_margin:.0f}")
    return {
        "agent": "casey",
        "action": "covered_today",
        "loads_covered": len(rows),
        "total_margin": round(total_margin, 2),
        "loads": rows,
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "find_coverage")
    if action == "find_coverage":
        return find_coverage(payload)
    if action == "call_carrier":
        return call_carrier(payload)
    if action == "confirm_coverage":
        return confirm_coverage(payload)
    if action == "covered_today":
        return covered_today(payload)
    return {"agent": "casey", "status": "error", "error": f"unknown action: {action}",
            "valid_actions": ["find_coverage", "call_carrier", "confirm_coverage", "covered_today"]}

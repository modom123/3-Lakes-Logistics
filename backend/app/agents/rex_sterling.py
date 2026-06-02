"""Rex Sterling — Head Trader · North America Trading Co.

Role: Head Trader at the North America Trading Co division of 3 Lakes Logistics.
Mission: Maximize trading desk profitability by monitoring open positions,
         auto-analyzing spread on every posted load, escalating stale trades,
         and generating the daily trading brief for Exec Command.

Powered by Qwen via OpenRouter; falls back to Claude then rule-based summary.

Payload keys (all optional):
  scope    str  "full" | "brief" | "positions" | "scan"   default: "full"
  load_id  str  (for scope="scan") analyze a specific NATCO load

Outputs (org memory):
  rex_sterling/morning_brief    — daily trading desk summary
  rex_sterling/open_positions   — current uncovered loads with age
  rex_sterling/mtd_pnl          — month-to-date gross and net
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import memory as mem

_NAME = "rex_sterling"
_DIVISION = "North America Trading Co"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = """You are Rex Sterling, Head Trader at North America Trading Co — the load trading division of 3 Lakes Logistics.

Your job: maximize broker-to-carrier spread (our gross profit on each load). You are direct, numbers-first, and always identify the highest-value actions.

Review the provided trading desk data and return ONLY a JSON object:
{
  "desk_health": <0-100>,
  "open_positions": <int>,
  "covered_today": <int>,
  "mtd_gross": <float>,
  "mtd_net": <float>,
  "avg_spread_today": <float>,
  "best_spread_load": {"load_number": "...", "spread": 0, "route": "..."},
  "stale_positions": [{"load_number": "...", "hours_open": 0, "broker_pay": 0, "route": "..."}],
  "alerts": [{"severity": "critical|high|medium", "message": "..."}],
  "recommended_actions": ["..."],
  "morning_brief": "<3-4 sentences: desk status, top opportunity, key risk, what traders should focus on today>"
}

Rules:
- Open position uncovered > 4 hours = high alert
- Open position uncovered > 8 hours = critical alert
- Spread below $200 on dry van = medium alert (thin margin)
- No loads posted today by 9am = high alert (desk idle)
- MTD gross 0 = critical (no revenue)
- Avg spread below $250 = flag (underperforming)"""


def _get_natco_loads() -> list[dict]:
    """Pull all loads tagged as NATCO trades."""
    try:
        db = get_supabase()
        res = db.table("loads").select("*").order("created_at", desc=True).limit(500).execute()
        loads = res.data or []
        return [l for l in loads if
                (l.get("load_number", "").startswith("NT-")) or
                ("[NATCO]" in (l.get("notes") or ""))]
    except Exception:
        return []


def _compute_stats(natco_loads: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    open_positions = []
    covered_today = 0
    mtd_gross = 0.0
    mtd_net = 0.0
    today_spreads = []

    for l in natco_loads:
        broker_pay = float(l.get("rate") or l.get("rate_total") or 0)
        carrier_pay = float(l.get("carrier_pay") or 0)
        spread = broker_pay - carrier_pay if carrier_pay else 0
        created = datetime.fromisoformat((l.get("created_at") or "").replace("Z", "+00:00")) if l.get("created_at") else None
        updated = datetime.fromisoformat((l.get("updated_at") or "").replace("Z", "+00:00")) if l.get("updated_at") else None

        # MTD stats
        ref_date = created or now
        if ref_date >= month_start:
            mtd_gross += broker_pay
            if carrier_pay:
                mtd_net += spread

        # Open positions (uncovered)
        status = (l.get("status") or "").lower()
        is_open = status in ("booked", "open", "") and not l.get("driver_name")
        if is_open and created:
            age_hours = (now - created).total_seconds() / 3600
            open_positions.append({
                "load_number": l.get("load_number", "?"),
                "hours_open": round(age_hours, 1),
                "broker_pay": broker_pay,
                "route": f"{l.get('origin','?')} → {l.get('destination','?')}",
                "equipment": l.get("equipment_type", "—"),
            })

        # Covered today
        ref = updated or created
        if ref and ref >= today_start and status in ("en route", "delivered", "completed", "covered"):
            covered_today += 1
            if carrier_pay:
                today_spreads.append(spread)

    best = max(natco_loads, key=lambda l: float(l.get("rate") or 0) - float(l.get("carrier_pay") or 0), default=None)

    return {
        "open_positions": open_positions,
        "covered_today": covered_today,
        "mtd_gross": round(mtd_gross, 2),
        "mtd_net": round(mtd_net, 2),
        "avg_spread_today": round(sum(today_spreads) / len(today_spreads), 2) if today_spreads else 0,
        "best_spread_load": {
            "load_number": best.get("load_number", "—") if best else "—",
            "spread": round(float(best.get("rate") or 0) - float(best.get("carrier_pay") or 0), 2) if best else 0,
            "route": f"{best.get('origin','?')} → {best.get('destination','?')}" if best else "—",
        } if best else None,
        "total_loads": len(natco_loads),
    }


def _call_qwen(stats: dict, scope: str) -> dict | None:
    s = get_settings()
    if not s.openrouter_api_key:
        return None
    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={"Authorization": f"Bearer {s.openrouter_api_key}", "Content-Type": "application/json"},
            json={
                "model": s.openrouter_model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": f"scope={scope}\n\nTrading desk data:\n{json.dumps(stats, indent=2)}"},
                ],
                "temperature": 0.3,
                "max_tokens": 600,
            },
            timeout=25,
        )
        raw = r.json()["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        return json.loads(raw)
    except Exception:
        return None


def _fallback_report(stats: dict) -> dict:
    open_pos = stats["open_positions"]
    stale = [p for p in open_pos if p["hours_open"] > 4]
    alerts = []
    for p in stale:
        sev = "critical" if p["hours_open"] > 8 else "high"
        alerts.append({"severity": sev, "message": f"Load {p['load_number']} uncovered for {p['hours_open']}h — {p['route']}"})
    if not stats["total_loads"]:
        alerts.append({"severity": "critical", "message": "No NATCO trades posted — desk is idle"})

    actions = []
    if stale:
        actions.append(f"Cover {len(stale)} stale position(s) immediately — contact available carriers")
    if stats["mtd_net"] == 0:
        actions.append("Post first trade to activate revenue stream")
    if stats["avg_spread_today"] < 250 and stats["covered_today"] > 0:
        actions.append("Review carrier pay rates — avg spread is thin")

    brief = (
        f"Trading desk has {len(open_pos)} open position(s) and {stats['covered_today']} covered today. "
        f"MTD gross: ${stats['mtd_gross']:,.0f} | Net: ${stats['mtd_net']:,.0f}. "
        f"{'CRITICAL: ' + str(len(stale)) + ' stale uncovered loads need immediate carrier outreach. ' if stale else ''}"
        f"Focus: {'cover stale positions first, then source new loads.' if stale else 'source new broker loads and maintain spread above $300.'}"
    )

    return {
        "desk_health": max(10, 100 - len(stale) * 20 - (10 if not stats["total_loads"] else 0)),
        "open_positions": len(open_pos),
        "covered_today": stats["covered_today"],
        "mtd_gross": stats["mtd_gross"],
        "mtd_net": stats["mtd_net"],
        "avg_spread_today": stats["avg_spread_today"],
        "best_spread_load": stats.get("best_spread_load"),
        "stale_positions": stale,
        "alerts": alerts,
        "recommended_actions": actions or ["Monitor open positions", "Source new broker loads"],
        "morning_brief": brief,
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    scope = payload.get("scope", "full")
    natco_loads = _get_natco_loads()
    stats = _compute_stats(natco_loads)

    report = _call_qwen(stats, scope) or _fallback_report(stats)

    # Write to org memory
    mem.write(_NAME, "morning_brief", report.get("morning_brief", ""))
    mem.write(_NAME, "open_positions", report.get("stale_positions", []))
    mem.write(_NAME, "mtd_pnl", {
        "gross": stats["mtd_gross"],
        "net": stats["mtd_net"],
        "avg_spread": stats["avg_spread_today"],
    })

    log_agent(_NAME, f"run.{scope}", result=f"health={report.get('desk_health',0)} open={report.get('open_positions',0)}")
    return {"agent": _NAME, "division": _DIVISION, "report": report}

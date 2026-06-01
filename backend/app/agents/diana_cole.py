"""Diana Cole — Node 200 · IEBC Light Fleet Division President

Specialty: Light Fleet Division oversight — NEMT, Medical Courier, Executive, Courier, Gig Fleet.
Mission: Consolidate all 5 segment manager reports into a division-level P&L snapshot and
         issue strategic directives to keep the division on target.

Powered by Qwen via OpenRouter; falls back to Claude then rule-based summary.

Payload keys (all optional):
  scope    str   "full" | "ops" | "finance" | "growth"   default: "full"
  top_n    int   number of top issues to surface          default: 5
  action   str   "report" | "directive"                  default: "report"

Outputs (org memory):
  diana_cole/division_report   — division-level P&L and ops snapshot
  diana_cole/directive         — strategic directive issued to segment managers
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import memory as mem

_NAME = "diana_cole"
_FIRM = "IEBC"
_NODE = 200
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = """You are Diana Cole, Node 200 of the IEBC Executive OS — President of the Light Fleet Division.
You oversee five segments: NEMT, Medical Courier, Executive & Black Car, Same-Day Courier, and Gig Fleet.

You are reviewing segment manager reports and live trip/revenue data to produce a division-level briefing.
Return ONLY a JSON object:
{
  "division_health": <0-100>,
  "revenue_summary": {"total_trips": 0, "estimated_revenue_usd": 0, "top_segment": ""},
  "ops_flags": [{"segment": "...", "issue": "...", "urgency": "critical|high|medium|low"}],
  "growth_opportunities": [{"segment": "...", "opportunity": "...", "action": "..."}],
  "directive": "<3 sentences — clear strategic instruction to all segment managers>",
  "summary": "<2 sentences — division health verdict>"
}

Rules:
- Any segment with 0 active trips is a critical ops flag
- Revenue below weekly run-rate is a high flag
- Growth opportunities should be specific and actionable
- Directive must reference at least 2 segments by name"""


def _gather_division_stats() -> dict:
    """Pull live trip counts and revenue estimates from Supabase across all segments."""
    stats: dict[str, Any] = {
        "nemt": {"trips": 0, "drivers": 0},
        "medical_courier": {"trips": 0, "drivers": 0},
        "executive": {"trips": 0, "drivers": 0},
        "courier": {"trips": 0, "drivers": 0},
        "gig": {"trips": 0, "drivers": 0},
        "total_trips": 0,
    }
    try:
        sb = get_supabase()
        # Active trips per segment
        for trip_type, key in [
            ("nemt", "nemt"),
            ("medical_courier", "medical_courier"),
            ("executive", "executive"),
            ("courier", "courier"),
            ("gig", "gig"),
        ]:
            res = (
                sb.table("light_vehicle_trips")
                .select("id", count="exact")
                .eq("trip_type", trip_type)
                .in_("status", ["pending", "in_progress", "assigned"])
                .execute()
            )
            count = res.count if res.count is not None else 0
            stats[key]["trips"] = count
            stats["total_trips"] += count

        # Active driver counts
        res = (
            sb.table("light_vehicle_drivers")
            .select("id", count="exact")
            .eq("status", "active")
            .execute()
        )
        stats["active_drivers"] = res.count if res.count is not None else 0
    except Exception as exc:
        stats["db_error"] = str(exc)
    return stats


def _read_segment_memory() -> dict:
    """Pull last reports from all 5 segment managers."""
    keys = [
        ("dr_james_nemt", "segment_report"),
        ("elena_ross", "segment_report"),
        ("victor_nash", "segment_report"),
        ("felix_grant", "segment_report"),
        ("morgan_hayes", "segment_report"),
    ]
    reports = {}
    for agent, key in keys:
        rec = mem.recall(agent, key)
        if rec:
            reports[agent] = rec
    # Also read Maya/Kai/Rio/Cash stats
    for agent, key in [
        ("maya", "last_intake"),
        ("kai", "last_sweep"),
        ("rio", "last_dispatch"),
        ("cash", "last_settlement"),
    ]:
        rec = mem.recall(agent, key)
        if rec:
            reports[f"{agent}_{key}"] = rec
    return reports


def _call_qwen(stats: dict, segment_reports: dict, scope: str, top_n: int) -> dict | None:
    s = get_settings()
    if not s.openrouter_api_key:
        return None
    context = json.dumps({
        "scope": scope,
        "top_n": top_n,
        "live_stats": stats,
        "segment_memory": {k: str(v)[:300] for k, v in segment_reports.items()},
    }, default=str)
    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {s.openrouter_api_key}",
                "HTTP-Referer": "https://3lakeslogistics.com",
                "X-Title": "3 Lakes Logistics — Diana Cole Division Report",
                "Content-Type": "application/json",
            },
            json={
                "model": s.openrouter_model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": f"Produce division report:\n\n{context}"},
                ],
                "temperature": 0.15,
                "max_tokens": 1000,
            },
            timeout=30,
        )
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
    except Exception:
        pass
    return None


def _call_claude(stats: dict, segment_reports: dict, scope: str) -> dict | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    try:
        context = json.dumps({"scope": scope, "stats": stats}, default=str)
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": s.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-haiku-20240307",
                "max_tokens": 800,
                "system": _SYSTEM,
                "messages": [{"role": "user", "content": f"Produce division report:\n\n{context}"}],
            },
            timeout=30,
        )
        if r.status_code == 200:
            content = r.json()["content"][0]["text"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
    except Exception:
        pass
    return None


def _rule_based_report(stats: dict) -> dict:
    ops_flags = []
    for seg in ["nemt", "medical_courier", "executive", "courier", "gig"]:
        if stats.get(seg, {}).get("trips", 0) == 0:
            ops_flags.append({"segment": seg, "issue": "0 active trips", "urgency": "critical"})
    total = stats.get("total_trips", 0)
    return {
        "division_health": max(40, 80 - len(ops_flags) * 10),
        "revenue_summary": {"total_trips": total, "estimated_revenue_usd": total * 28, "top_segment": "unknown"},
        "ops_flags": ops_flags,
        "growth_opportunities": [],
        "directive": "All segment managers: report active trip counts and driver availability immediately. Diana Cole requires updated segment data before issuing full directive.",
        "summary": f"Rule-based snapshot only — LLM unavailable. {len(ops_flags)} segments with 0 active trips detected.",
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "report")).lower()
    scope  = str(payload.get("scope", "full")).lower()
    top_n  = int(payload.get("top_n", 5))

    # Quick directive read
    if action == "directive":
        rec = mem.recall(_NAME, "directive")
        return {
            "agent": _NAME, "node": _NODE, "firm": _FIRM,
            "action": "directive",
            "directive": rec or {"directive": "No directive issued yet. Run full report first."},
        }

    stats           = _gather_division_stats()
    segment_reports = _read_segment_memory()

    llm_report = _call_qwen(stats, segment_reports, scope, top_n)
    if llm_report is None:
        llm_report = _call_claude(stats, segment_reports, scope)
    if llm_report is None:
        llm_report = _rule_based_report(stats)

    report = {
        "agent":     _NAME,
        "node":      _NODE,
        "firm":      _FIRM,
        "scope":     scope,
        "top_n":     top_n,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "live_stats":            stats,
        "division_health":       llm_report.get("division_health", 70),
        "revenue_summary":       llm_report.get("revenue_summary", {}),
        "ops_flags":             llm_report.get("ops_flags", [])[:top_n],
        "growth_opportunities":  llm_report.get("growth_opportunities", [])[:top_n],
        "directive":             llm_report.get("directive", ""),
        "summary":               llm_report.get("summary", ""),
        "segment_reports_read":  list(segment_reports.keys()),
        "llm_powered":           llm_report.get("directive", "") != "" and "Rule-based" not in llm_report.get("summary", ""),
    }

    mem.remember(
        _NAME, "division_report", report, confidence=0.9,
        summary=f"Diana division report: health={report['division_health']} trips={stats.get('total_trips',0)} flags={len(report['ops_flags'])}",
    )
    mem.remember(
        _NAME, "directive",
        {"directive": report["directive"], "scope": scope, "timestamp": report["timestamp"]},
        confidence=0.95,
        summary=report["directive"][:120] if report["directive"] else "No directive",
    )

    log_agent(
        _NAME, "division_report",
        payload={"scope": scope, "top_n": top_n},
        result=f"health={report['division_health']} total_trips={stats.get('total_trips',0)} flags={len(report['ops_flags'])}",
    )

    return report

"""Victor Nash — Node 203 · IEBC Executive & Black Car Segment Manager

Specialty: VIP, airport, and corporate transportation management.
Mission: Monitor executive corporate accounts, driver ratings and presentation standards,
         on-time performance for airport runs, and corporate billing health.

Powered by Qwen via OpenRouter; falls back to Claude then rule-based summary.

Payload keys (all optional):
  scope    str   "full" | "accounts" | "performance"   default: "full"
  action   str   "report" (default)

Outputs (org memory):
  victor_nash/segment_report   — full Executive & Black Car segment ops report
  victor_nash/client_alerts    — corporate account issues and performance warnings
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

_NAME = "victor_nash"
_FIRM = "IEBC"
_NODE = 203
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = """You are Victor Nash, Node 203 of the IEBC Executive OS — Executive & Black Car Segment Manager.
You manage VIP airport runs, corporate transportation accounts, and black car services.

Review the provided operational data and return ONLY a JSON object:
{
  "segment_health": <0-100>,
  "active_trips": <int>,
  "active_drivers": <int>,
  "on_time_pct": <float>,
  "avg_driver_rating": <float>,
  "client_alerts": [{"account": "...", "issue": "...", "urgency": "critical|high|medium"}],
  "performance_flags": [{"driver_id": "...", "issue": "...", "metric": "..."}],
  "account_summary": [{"account": "...", "status": "active|at_risk|churned", "monthly_trips": 0}],
  "ops_summary": "<2 sentences — Executive segment health verdict>",
  "recommended_actions": ["..."]
}

Rules:
- Driver rating below 4.5 on executive runs = high performance flag
- Airport run more than 10 min late = high flag (client SLA breach)
- Corporate account with no trips in 14 days = at_risk
- Unpaid corporate invoice > 30 days = critical client alert
- Driver without business attire note on executive profile = medium flag
- On-time performance below 95% = high flag for the segment"""


def _fetch_executive_data() -> dict:
    """Pull executive trips, accounts, and driver data from Supabase."""
    data: dict[str, Any] = {
        "active_trips": [],
        "completion_stats": {},
        "active_drivers": [],
        "corporate_accounts": [],
        "performance_concerns": [],
    }
    try:
        sb = get_supabase()
        now = datetime.now(timezone.utc)

        # Active executive trips
        trips_res = (
            sb.table("light_vehicle_trips")
            .select("id, status, driver_id, pickup_time, dropoff_time, trip_type, client_id, driver_rating, on_time")
            .eq("trip_type", "executive")
            .in_("status", ["pending", "in_progress", "assigned"])
            .order("pickup_time", desc=False)
            .limit(50)
            .execute()
        )
        data["active_trips"] = trips_res.data or []

        # Completion stats + on-time rate
        completed_res = (
            sb.table("light_vehicle_trips")
            .select("id, on_time, driver_rating", count="exact")
            .eq("trip_type", "executive")
            .eq("status", "completed")
            .execute()
        )
        completed_data = completed_res.data or []
        total_completed = completed_res.count or 0
        on_time_count = sum(1 for t in completed_data if t.get("on_time") is True)
        ratings = [t["driver_rating"] for t in completed_data if t.get("driver_rating") is not None]
        data["completion_stats"] = {
            "total_completed": total_completed,
            "on_time_count": on_time_count,
            "on_time_pct": round(on_time_count / total_completed * 100, 1) if total_completed > 0 else 100.0,
            "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0.0,
        }

        # Active executive / black car drivers
        drivers_res = (
            sb.table("light_vehicle_drivers")
            .select("id, name, status, approved_services, driver_rating, last_active")
            .eq("status", "active")
            .execute()
        )
        all_drivers = drivers_res.data or []
        exec_drivers = [
            d for d in all_drivers
            if "executive" in (d.get("approved_services") or [])
            or "black_car" in (d.get("approved_services") or [])
        ]
        data["active_drivers"] = exec_drivers

        # Flag low-rated drivers
        for driver in exec_drivers:
            rating = driver.get("driver_rating")
            if rating is not None and float(rating) < 4.5:
                data["performance_concerns"].append({
                    "driver_id": driver["id"],
                    "driver_name": driver.get("name", "Unknown"),
                    "issue": f"Driver rating {rating} below 4.5 executive standard",
                    "urgency": "high",
                })

        # Corporate accounts
        try:
            accounts_res = (
                sb.table("executive_accounts")
                .select("id, account_name, status, last_trip_date, outstanding_balance, contract_type")
                .eq("status", "active")
                .limit(30)
                .execute()
            )
            data["corporate_accounts"] = accounts_res.data or []

            # Flag at-risk accounts (no trips in 14 days)
            for acct in data["corporate_accounts"]:
                last_trip = acct.get("last_trip_date")
                balance = acct.get("outstanding_balance", 0) or 0
                if balance > 0:
                    # Check if invoice is overdue (simplified: any positive balance)
                    if float(balance) > 500:
                        data["performance_concerns"].append({
                            "account": acct.get("account_name", acct["id"]),
                            "issue": f"Outstanding balance ${balance} on corporate account",
                            "urgency": "critical" if float(balance) > 2000 else "high",
                        })
                if last_trip:
                    try:
                        last_dt = datetime.fromisoformat(str(last_trip).replace("Z", "+00:00"))
                        days_inactive = (now - last_dt).days
                        if days_inactive > 14:
                            data["performance_concerns"].append({
                                "account": acct.get("account_name", acct["id"]),
                                "issue": f"No trips in {days_inactive} days — account at risk",
                                "urgency": "medium",
                            })
                    except Exception:
                        pass
        except Exception:
            # executive_accounts table may not exist yet
            data["corporate_accounts"] = []

    except Exception as exc:
        data["db_error"] = str(exc)
    return data


def _call_qwen(exec_data: dict, scope: str) -> dict | None:
    s = get_settings()
    if not s.openrouter_api_key:
        return None
    context = json.dumps({
        "scope": scope,
        "active_trip_count": len(exec_data.get("active_trips", [])),
        "active_driver_count": len(exec_data.get("active_drivers", [])),
        "completion_stats": exec_data.get("completion_stats", {}),
        "performance_concerns": exec_data.get("performance_concerns", []),
        "corporate_account_count": len(exec_data.get("corporate_accounts", [])),
        "sample_trips": exec_data.get("active_trips", [])[:5],
    }, default=str)
    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {s.openrouter_api_key}",
                "HTTP-Referer": "https://3lakeslogistics.com",
                "X-Title": "3 Lakes Logistics — Victor Nash Executive Report",
                "Content-Type": "application/json",
            },
            json={
                "model": s.openrouter_model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": f"Generate Executive & Black Car segment report:\n\n{context}"},
                ],
                "temperature": 0.1,
                "max_tokens": 900,
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


def _call_claude(exec_data: dict, scope: str) -> dict | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    try:
        context = json.dumps({
            "scope": scope,
            "stats": exec_data.get("completion_stats", {}),
            "concerns": exec_data.get("performance_concerns", []),
        }, default=str)
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": s.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-haiku-20240307",
                "max_tokens": 700,
                "system": _SYSTEM,
                "messages": [{"role": "user", "content": f"Generate Executive segment report:\n\n{context}"}],
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


def _rule_based_report(exec_data: dict) -> dict:
    concerns = exec_data.get("performance_concerns", [])
    active = len(exec_data.get("active_trips", []))
    drivers = len(exec_data.get("active_drivers", []))
    stats = exec_data.get("completion_stats", {})
    on_time = stats.get("on_time_pct", 100.0)
    avg_rating = stats.get("avg_rating", 0.0)
    critical = [c for c in concerns if c.get("urgency") == "critical"]
    return {
        "segment_health": max(40, 90 - len(critical) * 10),
        "active_trips": active,
        "active_drivers": drivers,
        "on_time_pct": on_time,
        "avg_driver_rating": avg_rating,
        "client_alerts": [c for c in concerns if "account" in c],
        "performance_flags": [c for c in concerns if "driver_id" in c],
        "account_summary": [],
        "ops_summary": (
            f"Executive segment: {active} active trips, {drivers} drivers, "
            f"{on_time}% on-time, avg rating {avg_rating}. "
            f"{len(critical)} critical issues require attention."
        ),
        "recommended_actions": (
            ["Review outstanding corporate invoices", "Audit low-rated driver assignments"]
            if concerns else ["Executive segment performing within standards"]
        ),
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    scope = str(payload.get("scope", "full")).lower()

    exec_data = _fetch_executive_data()

    llm_report = _call_qwen(exec_data, scope)
    if llm_report is None:
        llm_report = _call_claude(exec_data, scope)
    if llm_report is None:
        llm_report = _rule_based_report(exec_data)

    client_alerts = llm_report.get("client_alerts", [c for c in exec_data.get("performance_concerns", []) if "account" in c])

    report = {
        "agent":     _NAME,
        "node":      _NODE,
        "firm":      _FIRM,
        "scope":     scope,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "segment":   "executive",
        "segment_health":      llm_report.get("segment_health", 70),
        "active_trips":        llm_report.get("active_trips", len(exec_data.get("active_trips", []))),
        "active_drivers":      llm_report.get("active_drivers", len(exec_data.get("active_drivers", []))),
        "on_time_pct":         llm_report.get("on_time_pct", exec_data.get("completion_stats", {}).get("on_time_pct", 0.0)),
        "avg_driver_rating":   llm_report.get("avg_driver_rating", exec_data.get("completion_stats", {}).get("avg_rating", 0.0)),
        "client_alerts":       client_alerts,
        "performance_flags":   llm_report.get("performance_flags", []),
        "account_summary":     llm_report.get("account_summary", []),
        "ops_summary":         llm_report.get("ops_summary", ""),
        "recommended_actions": llm_report.get("recommended_actions", []),
        "llm_powered":         "db_error" not in exec_data,
    }

    mem.remember(
        _NAME, "segment_report", report, confidence=0.88,
        summary=(
            f"Victor Nash report: health={report['segment_health']} trips={report['active_trips']} "
            f"on_time={report['on_time_pct']}% rating={report['avg_driver_rating']}"
        ),
    )
    mem.remember(
        _NAME, "client_alerts",
        {
            "alerts": client_alerts,
            "critical_count": len([a for a in client_alerts if a.get("urgency") == "critical"]),
            "timestamp": report["timestamp"],
        },
        confidence=0.92,
        summary=f"{len(client_alerts)} client alerts — {len([a for a in client_alerts if a.get('urgency') == 'critical'])} critical",
    )

    log_agent(
        _NAME, "executive_report",
        payload={"scope": scope},
        result=f"health={report['segment_health']} trips={report['active_trips']} on_time={report['on_time_pct']}% alerts={len(client_alerts)}",
    )

    return report

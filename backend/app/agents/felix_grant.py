"""Felix Grant — Node 204 · IEBC Same-Day Courier Segment Manager

Specialty: Curri and Roadie load pipeline management, same-day delivery operations.
Mission: Monitor loads available from Curri/Roadie, maximize acceptance rate, track delivery
         completion rate, and ensure driver coverage by city.

Powered by Qwen via OpenRouter; falls back to Claude then rule-based summary.

Payload keys (all optional):
  scope    str   "full" | "pipeline" | "coverage"   default: "full"
  action   str   "report" (default)

Outputs (org memory):
  felix_grant/segment_report   — full Same-Day Courier segment ops report
  felix_grant/load_pipeline    — Curri/Roadie load availability and acceptance metrics
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

_NAME = "felix_grant"
_FIRM = "IEBC"
_NODE = 204
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = """You are Felix Grant, Node 204 of the IEBC Executive OS — Same-Day Courier Segment Manager.
You manage the Curri and Roadie load pipeline: accepting loads, dispatching drivers, and
tracking same-day delivery completion.

Review the provided operational data and return ONLY a JSON object:
{
  "segment_health": <0-100>,
  "active_trips": <int>,
  "active_drivers": <int>,
  "acceptance_rate_pct": <float>,
  "completion_rate_pct": <float>,
  "pipeline_status": {"curri": "healthy|degraded|down", "roadie": "healthy|degraded|down"},
  "coverage_gaps": [{"city": "...", "available_drivers": 0, "pending_loads": 0}],
  "load_flags": [{"source": "curri|roadie", "issue": "...", "urgency": "critical|high|medium"}],
  "ops_summary": "<2 sentences — Same-Day Courier pipeline health verdict>",
  "recommended_actions": ["..."]
}

Rules:
- Acceptance rate below 70% = critical — loads are being left on the table
- Completion rate below 85% = high flag
- City with > 3 pending loads and 0 available drivers = critical coverage gap
- Curri or Roadie API returning no loads during business hours = high flag (possible API issue)
- Driver covering a city solo with > 5 loads queued = high flag (burnout risk)
- Any load pending acceptance for > 20 minutes = high urgency"""


def _fetch_courier_pipeline_data() -> dict:
    """Pull Curri/Roadie courier trips and driver data from Supabase."""
    data: dict[str, Any] = {
        "active_trips": [],
        "completion_stats": {},
        "acceptance_stats": {},
        "active_drivers": [],
        "city_coverage": {},
        "load_flags": [],
    }
    try:
        sb = get_supabase()
        now = datetime.now(timezone.utc)

        # Active Curri/Roadie trips
        trips_res = (
            sb.table("light_vehicle_trips")
            .select("id, status, driver_id, pickup_time, dropoff_time, trip_type, source, city, created_at")
            .eq("trip_type", "courier")
            .in_("source", ["curri", "roadie"])
            .in_("status", ["pending", "in_progress", "assigned"])
            .order("created_at", desc=False)
            .limit(100)
            .execute()
        )
        data["active_trips"] = trips_res.data or []

        # Completion stats
        completed_res = (
            sb.table("light_vehicle_trips")
            .select("id", count="exact")
            .eq("trip_type", "courier")
            .in_("source", ["curri", "roadie"])
            .eq("status", "completed")
            .execute()
        )
        all_closed_res = (
            sb.table("light_vehicle_trips")
            .select("id", count="exact")
            .eq("trip_type", "courier")
            .in_("source", ["curri", "roadie"])
            .in_("status", ["completed", "cancelled", "failed"])
            .execute()
        )
        completed = completed_res.count or 0
        total_closed = all_closed_res.count or 0
        data["completion_stats"] = {
            "completed": completed,
            "total_closed": total_closed,
            "rate_pct": round(completed / total_closed * 100, 1) if total_closed > 0 else 100.0,
        }

        # Acceptance stats — offered vs accepted
        offered_res = (
            sb.table("light_vehicle_trips")
            .select("id", count="exact")
            .eq("trip_type", "courier")
            .in_("source", ["curri", "roadie"])
            .in_("status", ["pending", "assigned", "in_progress", "completed", "cancelled", "failed", "declined"])
            .execute()
        )
        declined_res = (
            sb.table("light_vehicle_trips")
            .select("id", count="exact")
            .eq("trip_type", "courier")
            .in_("source", ["curri", "roadie"])
            .eq("status", "declined")
            .execute()
        )
        total_offered = offered_res.count or 0
        declined = declined_res.count or 0
        accepted = total_offered - declined
        data["acceptance_stats"] = {
            "total_offered": total_offered,
            "accepted": accepted,
            "declined": declined,
            "rate_pct": round(accepted / total_offered * 100, 1) if total_offered > 0 else 100.0,
        }

        # Active courier drivers
        drivers_res = (
            sb.table("light_vehicle_drivers")
            .select("id, name, status, approved_services, city, last_active")
            .eq("status", "active")
            .execute()
        )
        all_drivers = drivers_res.data or []
        courier_drivers = [
            d for d in all_drivers
            if "courier" in (d.get("approved_services") or [])
            or "same_day_courier" in (d.get("approved_services") or [])
        ]
        data["active_drivers"] = courier_drivers

        # City coverage analysis
        city_loads: dict[str, int] = {}
        city_drivers: dict[str, int] = {}
        for trip in data["active_trips"]:
            city = trip.get("city") or "unknown"
            city_loads[city] = city_loads.get(city, 0) + 1
        for driver in courier_drivers:
            city = driver.get("city") or "unknown"
            city_drivers[city] = city_drivers.get(city, 0) + 1
        for city, loads in city_loads.items():
            drivers_in_city = city_drivers.get(city, 0)
            data["city_coverage"][city] = {"loads": loads, "drivers": drivers_in_city}
            if loads >= 3 and drivers_in_city == 0:
                data["load_flags"].append({
                    "source": "coverage",
                    "issue": f"{city}: {loads} pending loads, 0 drivers available",
                    "urgency": "critical",
                    "city": city,
                    "pending_loads": loads,
                    "available_drivers": 0,
                })
            elif drivers_in_city == 1 and loads > 5:
                data["load_flags"].append({
                    "source": "coverage",
                    "issue": f"{city}: solo driver covering {loads} loads — burnout risk",
                    "urgency": "high",
                    "city": city,
                    "pending_loads": loads,
                    "available_drivers": drivers_in_city,
                })

        # Flag long-pending loads
        for trip in data["active_trips"]:
            if trip.get("status") == "pending":
                created = trip.get("created_at")
                if created:
                    try:
                        created_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                        pending_min = (now - created_dt).total_seconds() / 60
                        if pending_min > 20:
                            data["load_flags"].append({
                                "source": trip.get("source", "unknown"),
                                "issue": f"Load pending acceptance for {round(pending_min)}min",
                                "urgency": "high" if pending_min < 45 else "critical",
                                "trip_id": trip["id"],
                            })
                    except Exception:
                        pass

        # Read Kai's last courier sweep from memory for API health
        kai_sweep = mem.recall("kai", "last_sweep")
        if kai_sweep:
            data["kai_last_sweep"] = kai_sweep

    except Exception as exc:
        data["db_error"] = str(exc)
    return data


def _call_qwen(pipeline_data: dict, scope: str) -> dict | None:
    s = get_settings()
    if not s.openrouter_api_key:
        return None
    context = json.dumps({
        "scope": scope,
        "active_trip_count": len(pipeline_data.get("active_trips", [])),
        "active_driver_count": len(pipeline_data.get("active_drivers", [])),
        "completion_stats": pipeline_data.get("completion_stats", {}),
        "acceptance_stats": pipeline_data.get("acceptance_stats", {}),
        "city_coverage": pipeline_data.get("city_coverage", {}),
        "load_flags": pipeline_data.get("load_flags", []),
    }, default=str)
    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {s.openrouter_api_key}",
                "HTTP-Referer": "https://3lakeslogistics.com",
                "X-Title": "3 Lakes Logistics — Felix Grant Same-Day Courier Report",
                "Content-Type": "application/json",
            },
            json={
                "model": s.openrouter_model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": f"Generate Same-Day Courier segment report:\n\n{context}"},
                ],
                "temperature": 0.1,
                "max_tokens": 900,
            },
            timeout=30,
        )
        if r.status_code == 200:
            _d = r.json()
            _u = _d.get("usage", {})
            try:
                from ..cost_tracking import track_openrouter as _tor
                _tor(s.openrouter_model, _u.get("prompt_tokens", 0), _u.get("completion_tokens", 0), agent="felix_grant")
            except Exception:
                pass
            content = _d["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
    except Exception:
        pass
    return None


def _call_claude(pipeline_data: dict, scope: str) -> dict | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    try:
        context = json.dumps({
            "scope": scope,
            "completion_stats": pipeline_data.get("completion_stats", {}),
            "acceptance_stats": pipeline_data.get("acceptance_stats", {}),
            "load_flags": pipeline_data.get("load_flags", []),
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
                "messages": [{"role": "user", "content": f"Generate Same-Day Courier segment report:\n\n{context}"}],
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


def _rule_based_report(pipeline_data: dict) -> dict:
    flags = pipeline_data.get("load_flags", [])
    active = len(pipeline_data.get("active_trips", []))
    drivers = len(pipeline_data.get("active_drivers", []))
    accept = pipeline_data.get("acceptance_stats", {}).get("rate_pct", 100.0)
    complete = pipeline_data.get("completion_stats", {}).get("rate_pct", 100.0)
    critical = [f for f in flags if f.get("urgency") == "critical"]
    coverage_gaps = [
        {"city": f.get("city", "unknown"), "available_drivers": f.get("available_drivers", 0), "pending_loads": f.get("pending_loads", 0)}
        for f in flags if "coverage" in f.get("source", "")
    ]
    return {
        "segment_health": max(30, 85 - len(critical) * 12),
        "active_trips": active,
        "active_drivers": drivers,
        "acceptance_rate_pct": accept,
        "completion_rate_pct": complete,
        "pipeline_status": {"curri": "unknown", "roadie": "unknown"},
        "coverage_gaps": coverage_gaps,
        "load_flags": flags,
        "ops_summary": (
            f"Same-Day Courier: {active} active loads, {drivers} drivers, "
            f"{accept}% acceptance, {complete}% completion. "
            f"{len(critical)} critical pipeline issues."
        ),
        "recommended_actions": (
            ["Dispatch drivers to coverage gaps immediately", "Review load acceptance speed"]
            if flags else ["Courier pipeline operating normally"]
        ),
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    scope = str(payload.get("scope", "full")).lower()

    pipeline_data = _fetch_courier_pipeline_data()

    llm_report = _call_qwen(pipeline_data, scope)
    if llm_report is None:
        llm_report = _call_claude(pipeline_data, scope)
    if llm_report is None:
        llm_report = _rule_based_report(pipeline_data)

    load_flags = llm_report.get("load_flags", pipeline_data.get("load_flags", []))

    report = {
        "agent":     _NAME,
        "node":      _NODE,
        "firm":      _FIRM,
        "scope":     scope,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "segment":   "same_day_courier",
        "segment_health":       llm_report.get("segment_health", 70),
        "active_trips":         llm_report.get("active_trips", len(pipeline_data.get("active_trips", []))),
        "active_drivers":       llm_report.get("active_drivers", len(pipeline_data.get("active_drivers", []))),
        "acceptance_rate_pct":  llm_report.get("acceptance_rate_pct", pipeline_data.get("acceptance_stats", {}).get("rate_pct", 0.0)),
        "completion_rate_pct":  llm_report.get("completion_rate_pct", pipeline_data.get("completion_stats", {}).get("rate_pct", 0.0)),
        "pipeline_status":      llm_report.get("pipeline_status", {"curri": "unknown", "roadie": "unknown"}),
        "coverage_gaps":        llm_report.get("coverage_gaps", []),
        "load_flags":           load_flags,
        "ops_summary":          llm_report.get("ops_summary", ""),
        "recommended_actions":  llm_report.get("recommended_actions", []),
        "raw_acceptance_stats": pipeline_data.get("acceptance_stats", {}),
        "raw_completion_stats": pipeline_data.get("completion_stats", {}),
        "llm_powered":          "db_error" not in pipeline_data,
    }

    mem.remember(
        _NAME, "segment_report", report, confidence=0.88,
        summary=(
            f"Felix Grant report: health={report['segment_health']} trips={report['active_trips']} "
            f"accept={report['acceptance_rate_pct']}% complete={report['completion_rate_pct']}%"
        ),
    )
    mem.remember(
        _NAME, "load_pipeline",
        {
            "pipeline_status": report["pipeline_status"],
            "acceptance_stats": pipeline_data.get("acceptance_stats", {}),
            "completion_stats": pipeline_data.get("completion_stats", {}),
            "coverage_gaps": report["coverage_gaps"],
            "load_flags": load_flags,
            "timestamp": report["timestamp"],
        },
        confidence=0.9,
        summary=(
            f"Pipeline: accept={report['acceptance_rate_pct']}% complete={report['completion_rate_pct']}% "
            f"flags={len(load_flags)} gaps={len(report['coverage_gaps'])}"
        ),
    )

    log_agent(
        _NAME, "same_day_courier_report",
        payload={"scope": scope},
        result=(
            f"health={report['segment_health']} trips={report['active_trips']} "
            f"accept={report['acceptance_rate_pct']}% flags={len(load_flags)}"
        ),
    )

    return report

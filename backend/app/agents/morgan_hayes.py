"""Morgan Hayes — Node 205 · IEBC Gig Fleet Management Segment Manager

Specialty: Multi-platform gig fleet utilization, driver earnings optimization.
Mission: Monitor gig driver utilization across all platforms, track earnings per driver,
         identify underperforming drivers, and maximize fleet-wide revenue per hour.

Powered by Qwen via OpenRouter; falls back to Claude then rule-based summary.

Payload keys (all optional):
  scope    str   "full" | "utilization" | "earnings"   default: "full"
  action   str   "report" (default)

Outputs (org memory):
  morgan_hayes/segment_report   — full Gig Fleet segment ops report
  morgan_hayes/utilization      — per-driver utilization and earnings stats
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

_NAME = "morgan_hayes"
_FIRM = "IEBC"
_NODE = 205
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = """You are Morgan Hayes, Node 205 of the IEBC Executive OS — Gig Fleet Management Segment Manager.
You oversee multi-vehicle independent contractor drivers who work across gig platforms.

Review the provided operational data and return ONLY a JSON object:
{
  "segment_health": <0-100>,
  "active_drivers": <int>,
  "inactive_drivers": <int>,
  "trips_last_7d": <int>,
  "avg_earnings_per_driver": <float>,
  "avg_trips_per_driver": <float>,
  "utilization_pct": <float>,
  "driver_alerts": [{"driver_id": "...", "issue": "...", "urgency": "critical|high|medium"}],
  "ops_summary": "<2 sentences — Gig Fleet segment health verdict>",
  "recommended_actions": ["..."]
}

Rules:
- Driver with zero trips in 7 days but status=active = medium alert (inactive driver)
- Driver earnings below $100 in last 7 days = medium alert
- Driver with suspended or flagged MVR = critical alert
- Fleet utilization below 40% = high alert
- More than 30% of enrolled drivers inactive in last 3 days = high alert
- Driver with rating below 4.0 = high alert"""


def _fetch_gig_data() -> dict:
    data: dict[str, Any] = {
        "active_drivers": [],
        "inactive_drivers": [],
        "recent_trips": [],
        "driver_earnings": [],
    }
    try:
        sb = get_supabase()
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        drivers_res = (
            sb.table("light_vehicle_drivers")
            .select("id, name, status, approved_services, rating, total_trips, mvr_status, plan")
            .execute()
        )
        all_drivers = drivers_res.data or []
        gig_drivers = [
            d for d in all_drivers
            if "gig" in (d.get("approved_services") or [])
        ]
        data["active_drivers"] = [d for d in gig_drivers if d.get("status") == "active"]
        data["inactive_drivers"] = [d for d in gig_drivers if d.get("status") != "active"]

        trips_res = (
            sb.table("light_vehicle_trips")
            .select("id, driver_id, status, trip_type, driver_payout, completed_at, source")
            .eq("trip_type", "gig")
            .gte("completed_at", week_ago)
            .execute()
        )
        data["recent_trips"] = trips_res.data or []

        # Per-driver earnings map
        earnings: dict[str, float] = {}
        trip_counts: dict[str, int] = {}
        for t in data["recent_trips"]:
            did = t.get("driver_id")
            if not did:
                continue
            earnings[did] = earnings.get(did, 0.0) + float(t.get("driver_payout") or 0)
            trip_counts[did] = trip_counts.get(did, 0) + 1
        data["earnings_map"] = earnings
        data["trip_count_map"] = trip_counts

        # Flag drivers with issues
        alerts = []
        for d in data["active_drivers"]:
            did = d["id"]
            if d.get("mvr_status") in ("flagged",):
                alerts.append({"driver_id": did, "issue": f"MVR flagged for {d.get('name')}", "urgency": "critical"})
            rating = d.get("rating")
            if rating is not None and float(rating) < 4.0:
                alerts.append({"driver_id": did, "issue": f"Rating {rating} below 4.0 minimum", "urgency": "high"})
            if trip_counts.get(did, 0) == 0:
                alerts.append({"driver_id": did, "issue": f"{d.get('name')} has no trips in 7 days", "urgency": "medium"})
            elif earnings.get(did, 0) < 100:
                alerts.append({"driver_id": did, "issue": f"{d.get('name')} earned ${earnings.get(did, 0):.0f} in 7 days", "urgency": "medium"})
        data["alerts"] = alerts

    except Exception as exc:
        data["db_error"] = str(exc)
    return data


def _call_qwen(gig_data: dict, scope: str) -> dict | None:
    s = get_settings()
    if not s.openrouter_api_key:
        return None
    active = gig_data.get("active_drivers", [])
    inactive = gig_data.get("inactive_drivers", [])
    trips = gig_data.get("recent_trips", [])
    earnings_map = gig_data.get("earnings_map", {})
    avg_earnings = (sum(earnings_map.values()) / len(earnings_map)) if earnings_map else 0.0
    utilization = (len([d for d in active if gig_data.get("trip_count_map", {}).get(d["id"], 0) > 0]) / len(active) * 100) if active else 0.0

    context = json.dumps({
        "scope": scope,
        "active_driver_count": len(active),
        "inactive_driver_count": len(inactive),
        "trips_last_7d": len(trips),
        "avg_earnings_per_driver": round(avg_earnings, 2),
        "utilization_pct": round(utilization, 1),
        "alert_count": len(gig_data.get("alerts", [])),
        "sample_alerts": gig_data.get("alerts", [])[:5],
    }, default=str)
    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {s.openrouter_api_key}",
                "HTTP-Referer": "https://3lakeslogistics.com",
                "X-Title": "3 Lakes Logistics — Morgan Hayes Gig Fleet Report",
                "Content-Type": "application/json",
            },
            json={
                "model": s.openrouter_model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": f"Generate Gig Fleet segment report:\n\n{context}"},
                ],
                "temperature": 0.1,
                "max_tokens": 800,
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


def _call_claude(gig_data: dict, scope: str) -> dict | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    try:
        active = gig_data.get("active_drivers", [])
        trips = gig_data.get("recent_trips", [])
        context = json.dumps({
            "scope": scope,
            "active_drivers": len(active),
            "trips_last_7d": len(trips),
            "alerts": gig_data.get("alerts", [])[:5],
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
                "messages": [{"role": "user", "content": f"Generate Gig Fleet segment report:\n\n{context}"}],
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


def _rule_based_report(gig_data: dict) -> dict:
    active = gig_data.get("active_drivers", [])
    inactive = gig_data.get("inactive_drivers", [])
    trips = gig_data.get("recent_trips", [])
    alerts = gig_data.get("alerts", [])
    earnings_map = gig_data.get("earnings_map", {})
    trip_count_map = gig_data.get("trip_count_map", {})
    avg_earnings = (sum(earnings_map.values()) / len(earnings_map)) if earnings_map else 0.0
    active_working = len([d for d in active if trip_count_map.get(d["id"], 0) > 0])
    utilization = (active_working / len(active) * 100) if active else 0.0
    avg_trips = (len(trips) / len(active)) if active else 0.0
    critical = [a for a in alerts if a.get("urgency") == "critical"]
    return {
        "segment_health": max(40, 85 - len(critical) * 20 - (1 if utilization < 40 else 0) * 10),
        "active_drivers": len(active),
        "inactive_drivers": len(inactive),
        "trips_last_7d": len(trips),
        "avg_earnings_per_driver": round(avg_earnings, 2),
        "avg_trips_per_driver": round(avg_trips, 1),
        "utilization_pct": round(utilization, 1),
        "driver_alerts": alerts[:10],
        "ops_summary": (
            f"Gig Fleet: {len(active)} active drivers, {len(trips)} trips in 7 days, "
            f"{utilization:.0f}% utilization. {len(critical)} critical driver issues."
        ),
        "recommended_actions": (
            ["Review flagged MVR drivers", "Re-engage inactive drivers with outreach"]
            if alerts else ["Gig fleet operating within normal parameters"]
        ),
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    scope = str(payload.get("scope", "full")).lower()

    gig_data = _fetch_gig_data()

    llm_report = _call_qwen(gig_data, scope)
    if llm_report is None:
        llm_report = _call_claude(gig_data, scope)
    if llm_report is None:
        llm_report = _rule_based_report(gig_data)

    active = gig_data.get("active_drivers", [])
    inactive = gig_data.get("inactive_drivers", [])
    trips = gig_data.get("recent_trips", [])
    earnings_map = gig_data.get("earnings_map", {})
    avg_earnings = (sum(earnings_map.values()) / len(earnings_map)) if earnings_map else 0.0
    active_working = len([d for d in active if gig_data.get("trip_count_map", {}).get(d["id"], 0) > 0])
    utilization = (active_working / len(active) * 100) if active else 0.0

    report = {
        "agent":     _NAME,
        "node":      _NODE,
        "firm":      _FIRM,
        "scope":     scope,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "segment":   "gig",
        "segment_health":          llm_report.get("segment_health", 70),
        "active_drivers":          llm_report.get("active_drivers", len(active)),
        "inactive_drivers":        llm_report.get("inactive_drivers", len(inactive)),
        "trips_last_7d":           llm_report.get("trips_last_7d", len(trips)),
        "avg_earnings_per_driver": llm_report.get("avg_earnings_per_driver", round(avg_earnings, 2)),
        "avg_trips_per_driver":    llm_report.get("avg_trips_per_driver", 0.0),
        "utilization_pct":         llm_report.get("utilization_pct", round(utilization, 1)),
        "driver_alerts":           llm_report.get("driver_alerts", gig_data.get("alerts", [])),
        "ops_summary":             llm_report.get("ops_summary", ""),
        "recommended_actions":     llm_report.get("recommended_actions", []),
        "llm_powered":             "db_error" not in gig_data,
    }

    mem.remember(
        _NAME, "segment_report", report, confidence=0.88,
        summary=(
            f"Morgan Hayes report: health={report['segment_health']} drivers={report['active_drivers']} "
            f"trips_7d={report['trips_last_7d']} utilization={report['utilization_pct']}%"
        ),
    )
    mem.remember(
        _NAME, "utilization",
        {
            "active_drivers": report["active_drivers"],
            "utilization_pct": report["utilization_pct"],
            "avg_earnings_per_driver": report["avg_earnings_per_driver"],
            "alerts": report["driver_alerts"],
            "timestamp": report["timestamp"],
        },
        confidence=0.90,
        summary=f"Gig utilization: {report['utilization_pct']}%, avg earnings ${report['avg_earnings_per_driver']}/week",
    )

    log_agent(
        _NAME, "gig_fleet_report",
        payload={"scope": scope},
        result=f"health={report['segment_health']} drivers={report['active_drivers']} utilization={report['utilization_pct']}%",
    )

    return report

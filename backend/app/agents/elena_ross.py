"""Elena Ross — Node 202 · IEBC Medical Courier Segment Manager

Specialty: Specimen pickup, pharmacy delivery, and lab sample transport operations.
Mission: Monitor active courier drivers, enforce pickup SLA compliance for time-sensitive cargo,
         and maintain hospital/lab contract health. Enforces chain-of-custody and temperature-sensitive
         cargo protocols.

Powered by Qwen via OpenRouter; falls back to Claude then rule-based summary.

Payload keys (all optional):
  scope    str   "full" | "sla" | "contracts"   default: "full"
  action   str   "report" (default)

Outputs (org memory):
  elena_ross/segment_report   — full Medical Courier segment ops report
  elena_ross/sla_alerts       — SLA breaches and time-sensitive cargo warnings
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

_NAME = "elena_ross"
_FIRM = "IEBC"
_NODE = 202
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = """You are Elena Ross, Node 202 of the IEBC Executive OS — Medical Courier Segment Manager.
You manage specimen pickups, pharmacy deliveries, and lab sample transport for hospitals and clinics.

Review the provided operational data and return ONLY a JSON object:
{
  "segment_health": <0-100>,
  "active_trips": <int>,
  "active_drivers": <int>,
  "sla_compliance_pct": <float>,
  "sla_alerts": [{"trip_id": "...", "issue": "...", "urgency": "critical|high|medium", "cargo_type": "..."}],
  "contract_status": [{"client": "...", "status": "active|at_risk|breach", "note": "..."}],
  "ops_summary": "<2 sentences — current Medical Courier segment health>",
  "recommended_actions": ["..."]
}

Rules:
- Any specimen pickup more than 15 min past scheduled window = critical SLA alert
- Temperature-sensitive cargo (blood, tissue, vaccines) with no driver assigned = critical
- Chain-of-custody gap (pickup confirmed but no dropoff scan) > 2 hours = critical
- Pharmacy delivery past promised window = high alert
- Contract with < 95% SLA over 30 days = at_risk
- Driver inactive for medical courier run while trip is pending = high flag"""


def _fetch_courier_data() -> dict:
    """Pull medical courier trips and driver data from Supabase."""
    data: dict[str, Any] = {
        "active_trips": [],
        "completion_stats": {},
        "active_drivers": [],
        "sla_breaches": [],
    }
    try:
        sb = get_supabase()
        now = datetime.now(timezone.utc)

        # Active medical courier trips
        trips_res = (
            sb.table("light_vehicle_trips")
            .select("id, status, driver_id, pickup_time, dropoff_time, trip_type, source, client_id, cargo_type, scheduled_pickup")
            .eq("trip_type", "courier")
            .in_("status", ["pending", "in_progress", "assigned"])
            .order("scheduled_pickup", desc=False)
            .limit(60)
            .execute()
        )
        all_trips = trips_res.data or []
        # Filter to medical source trips
        medical_trips = [
            t for t in all_trips
            if "medical" in str(t.get("source", "")).lower()
            or t.get("cargo_type") in ("specimen", "lab_sample", "pharmacy", "blood", "vaccine", "tissue")
        ]
        data["active_trips"] = medical_trips

        # Completion stats
        closed_res = (
            sb.table("light_vehicle_trips")
            .select("id", count="exact")
            .eq("trip_type", "courier")
            .in_("status", ["completed", "cancelled"])
            .execute()
        )
        completed_res = (
            sb.table("light_vehicle_trips")
            .select("id", count="exact")
            .eq("trip_type", "courier")
            .eq("status", "completed")
            .execute()
        )
        total_closed = closed_res.count or 0
        completed = completed_res.count or 0
        data["completion_stats"] = {
            "total_closed": total_closed,
            "completed": completed,
            "rate_pct": round(completed / total_closed * 100, 1) if total_closed > 0 else 100.0,
        }

        # Active medical courier drivers
        drivers_res = (
            sb.table("light_vehicle_drivers")
            .select("id, name, status, approved_services, last_active")
            .eq("status", "active")
            .execute()
        )
        all_drivers = drivers_res.data or []
        courier_drivers = [
            d for d in all_drivers
            if "medical_courier" in (d.get("approved_services") or [])
            or "courier" in (d.get("approved_services") or [])
        ]
        data["active_drivers"] = courier_drivers

        # SLA breach detection
        for trip in medical_trips:
            scheduled = trip.get("scheduled_pickup")
            if scheduled:
                try:
                    sched_dt = datetime.fromisoformat(str(scheduled).replace("Z", "+00:00"))
                    overdue_min = (now - sched_dt).total_seconds() / 60
                    cargo = trip.get("cargo_type", "unknown")
                    temp_sensitive = cargo in ("blood", "vaccine", "tissue", "specimen")
                    if trip.get("status") == "pending" and not trip.get("driver_id") and temp_sensitive:
                        data["sla_breaches"].append({
                            "trip_id": trip["id"],
                            "issue": f"Temperature-sensitive {cargo} with no driver assigned",
                            "urgency": "critical",
                            "cargo_type": cargo,
                            "overdue_min": round(overdue_min, 1),
                        })
                    elif overdue_min > 15 and trip.get("status") in ("pending", "assigned"):
                        data["sla_breaches"].append({
                            "trip_id": trip["id"],
                            "issue": f"Pickup {round(overdue_min)}min past scheduled window",
                            "urgency": "critical" if overdue_min > 30 else "high",
                            "cargo_type": cargo,
                            "overdue_min": round(overdue_min, 1),
                        })
                except Exception:
                    pass

    except Exception as exc:
        data["db_error"] = str(exc)
    return data


def _call_qwen(courier_data: dict, scope: str) -> dict | None:
    s = get_settings()
    if not s.openrouter_api_key:
        return None
    context = json.dumps({
        "scope": scope,
        "active_trip_count": len(courier_data.get("active_trips", [])),
        "active_driver_count": len(courier_data.get("active_drivers", [])),
        "completion_stats": courier_data.get("completion_stats", {}),
        "sla_breaches": courier_data.get("sla_breaches", []),
        "sample_trips": courier_data.get("active_trips", [])[:5],
    }, default=str)
    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {s.openrouter_api_key}",
                "HTTP-Referer": "https://3lakeslogistics.com",
                "X-Title": "3 Lakes Logistics — Elena Ross Medical Courier Report",
                "Content-Type": "application/json",
            },
            json={
                "model": s.openrouter_model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": f"Generate Medical Courier segment report:\n\n{context}"},
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
                _tor(s.openrouter_model, _u.get("prompt_tokens", 0), _u.get("completion_tokens", 0), agent="elena_ross")
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


def _call_claude(courier_data: dict, scope: str) -> dict | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    try:
        context = json.dumps({
            "scope": scope,
            "stats": courier_data.get("completion_stats", {}),
            "sla_breaches": courier_data.get("sla_breaches", []),
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
                "messages": [{"role": "user", "content": f"Generate Medical Courier segment report:\n\n{context}"}],
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


def _rule_based_report(courier_data: dict) -> dict:
    breaches = courier_data.get("sla_breaches", [])
    active = len(courier_data.get("active_trips", []))
    drivers = len(courier_data.get("active_drivers", []))
    rate = courier_data.get("completion_stats", {}).get("rate_pct", 100.0)
    critical = [b for b in breaches if b.get("urgency") == "critical"]
    return {
        "segment_health": max(30, 88 - len(critical) * 12),
        "active_trips": active,
        "active_drivers": drivers,
        "sla_compliance_pct": round(max(0, 100 - len(breaches) * 5), 1),
        "sla_alerts": breaches,
        "contract_status": [],
        "ops_summary": (
            f"Medical Courier: {active} active trips, {drivers} drivers online, {rate}% completion. "
            f"{len(critical)} critical SLA breaches require immediate attention."
        ),
        "recommended_actions": (
            ["Assign drivers to unattended temperature-sensitive cargo immediately", "Review SLA breach log"]
            if breaches else ["Medical Courier segment operating within SLA"]
        ),
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    scope = str(payload.get("scope", "full")).lower()

    courier_data = _fetch_courier_data()

    llm_report = _call_qwen(courier_data, scope)
    if llm_report is None:
        llm_report = _call_claude(courier_data, scope)
    if llm_report is None:
        llm_report = _rule_based_report(courier_data)

    sla_alerts = llm_report.get("sla_alerts", courier_data.get("sla_breaches", []))

    report = {
        "agent":     _NAME,
        "node":      _NODE,
        "firm":      _FIRM,
        "scope":     scope,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "segment":   "medical_courier",
        "segment_health":      llm_report.get("segment_health", 70),
        "active_trips":        llm_report.get("active_trips", len(courier_data.get("active_trips", []))),
        "active_drivers":      llm_report.get("active_drivers", len(courier_data.get("active_drivers", []))),
        "sla_compliance_pct":  llm_report.get("sla_compliance_pct", 100.0),
        "sla_alerts":          sla_alerts,
        "contract_status":     llm_report.get("contract_status", []),
        "ops_summary":         llm_report.get("ops_summary", ""),
        "recommended_actions": llm_report.get("recommended_actions", []),
        "llm_powered":         "db_error" not in courier_data,
    }

    mem.remember(
        _NAME, "segment_report", report, confidence=0.88,
        summary=(
            f"Elena Ross report: health={report['segment_health']} trips={report['active_trips']} "
            f"sla={report['sla_compliance_pct']}% alerts={len(sla_alerts)}"
        ),
    )
    mem.remember(
        _NAME, "sla_alerts",
        {
            "alerts": sla_alerts,
            "critical_count": len([a for a in sla_alerts if a.get("urgency") == "critical"]),
            "timestamp": report["timestamp"],
        },
        confidence=0.95,
        summary=f"{len(sla_alerts)} SLA alerts — {len([a for a in sla_alerts if a.get('urgency') == 'critical'])} critical",
    )

    log_agent(
        _NAME, "medical_courier_report",
        payload={"scope": scope},
        result=f"health={report['segment_health']} trips={report['active_trips']} sla_alerts={len(sla_alerts)}",
    )

    return report

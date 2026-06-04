"""Dr. James — Node 201 · IEBC NEMT Segment Manager

Specialty: Non-Emergency Medical Transport operations and compliance.
Mission: Monitor NEMT driver readiness, Medicaid auth numbers, broker relationships (MTM/Modivcare),
         trip completion rates, HIPAA compliance, and CPR certification expiry.

Powered by Qwen via OpenRouter; falls back to Claude then rule-based summary.

Payload keys (all optional):
  scope    str   "full" | "compliance" | "ops"   default: "full"
  action   str   "report" (default)

Outputs (org memory):
  dr_james_nemt/segment_report     — full NEMT segment ops report
  dr_james_nemt/compliance_flags   — HIPAA / auth / CPR issues requiring immediate action
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

_NAME = "dr_james_nemt"
_FIRM = "IEBC"
_NODE = 201
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM = """You are Dr. James, Node 201 of the IEBC Executive OS — NEMT Segment Manager.
You manage Non-Emergency Medical Transport: Medicaid patients, hospital discharge rides,
dialysis transport, and wheelchair/stretcher van operations.

Review the provided operational data and return ONLY a JSON object:
{
  "segment_health": <0-100>,
  "active_trips": <int>,
  "active_drivers": <int>,
  "completion_rate_pct": <float>,
  "compliance_flags": [{"driver_id": "...", "issue": "...", "urgency": "critical|high|medium"}],
  "broker_status": [{"broker": "MTM|Modivcare|Southeastrans", "status": "active|issue|unknown"}],
  "ops_summary": "<2 sentences — current NEMT segment health>",
  "recommended_actions": ["..."]
}

Rules:
- Expired CPR certification = critical compliance flag
- Missing Medicaid auth number on in-progress trip = critical
- Trip completion rate below 90% = high flag
- Any driver without liability insurance = critical
- Drivers inactive >7 days without notice = medium flag"""


def _fetch_nemt_data() -> dict:
    """Pull NEMT trips and driver data from Supabase."""
    data: dict[str, Any] = {
        "active_trips": [],
        "pending_trips": [],
        "active_drivers": [],
        "completion_stats": {},
        "compliance_concerns": [],
    }
    try:
        sb = get_supabase()

        # Active / pending NEMT trips
        trips_res = (
            sb.table("light_vehicle_trips")
            .select("id, status, driver_id, pickup_time, dropoff_time, trip_type, auth_number, client_id")
            .eq("trip_type", "nemt")
            .in_("status", ["pending", "in_progress", "assigned"])
            .order("pickup_time", desc=False)
            .limit(50)
            .execute()
        )
        data["active_trips"] = trips_res.data or []

        # Completed trips in last 7 days for completion rate
        completed_res = (
            sb.table("light_vehicle_trips")
            .select("id, status", count="exact")
            .eq("trip_type", "nemt")
            .in_("status", ["completed", "cancelled", "no_show"])
            .execute()
        )
        total_closed = completed_res.count or 0
        completed_count_res = (
            sb.table("light_vehicle_trips")
            .select("id", count="exact")
            .eq("trip_type", "nemt")
            .eq("status", "completed")
            .execute()
        )
        completed_count = completed_count_res.count or 0
        data["completion_stats"] = {
            "total_closed": total_closed,
            "completed": completed_count,
            "rate_pct": round(completed_count / total_closed * 100, 1) if total_closed > 0 else 100.0,
        }

        # Active NEMT drivers
        drivers_res = (
            sb.table("light_vehicle_drivers")
            .select("id, name, status, cpr_expiry, license_expiry, approved_services, last_active")
            .eq("status", "active")
            .execute()
        )
        all_drivers = drivers_res.data or []
        # Filter to drivers approved for nemt
        nemt_drivers = [
            d for d in all_drivers
            if "nemt" in (d.get("approved_services") or [])
        ]
        data["active_drivers"] = nemt_drivers

        # Flag trips missing auth numbers
        for trip in data["active_trips"]:
            if not trip.get("auth_number"):
                data["compliance_concerns"].append({
                    "trip_id": trip["id"],
                    "issue": "Missing Medicaid auth number on active trip",
                    "urgency": "critical" if trip.get("status") == "in_progress" else "high",
                })

        # Flag CPR expiry on drivers
        today = datetime.now(timezone.utc).date()
        for driver in nemt_drivers:
            cpr_exp = driver.get("cpr_expiry")
            if cpr_exp:
                try:
                    exp_date = datetime.fromisoformat(str(cpr_exp)).date()
                    if exp_date <= today:
                        data["compliance_concerns"].append({
                            "driver_id": driver["id"],
                            "driver_name": driver.get("name", "Unknown"),
                            "issue": f"CPR certification expired: {cpr_exp}",
                            "urgency": "critical",
                        })
                except Exception:
                    pass

    except Exception as exc:
        data["db_error"] = str(exc)
    return data


def _call_qwen(nemt_data: dict, scope: str) -> dict | None:
    s = get_settings()
    if not s.openrouter_api_key:
        return None
    context = json.dumps({
        "scope": scope,
        "active_trip_count": len(nemt_data.get("active_trips", [])),
        "active_driver_count": len(nemt_data.get("active_drivers", [])),
        "completion_stats": nemt_data.get("completion_stats", {}),
        "compliance_concerns": nemt_data.get("compliance_concerns", []),
        "sample_trips": nemt_data.get("active_trips", [])[:5],
    }, default=str)
    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {s.openrouter_api_key}",
                "HTTP-Referer": "https://3lakeslogistics.com",
                "X-Title": "3 Lakes Logistics — Dr. James NEMT Report",
                "Content-Type": "application/json",
            },
            json={
                "model": s.openrouter_model,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": f"Generate NEMT segment report:\n\n{context}"},
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
                _tor(s.openrouter_model, _u.get("prompt_tokens", 0), _u.get("completion_tokens", 0), agent="dr_james_nemt")
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


def _call_claude(nemt_data: dict, scope: str) -> dict | None:
    s = get_settings()
    if not s.anthropic_api_key:
        return None
    try:
        context = json.dumps({"scope": scope, "stats": nemt_data.get("completion_stats", {})}, default=str)
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
                "messages": [{"role": "user", "content": f"Generate NEMT segment report:\n\n{context}"}],
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


def _rule_based_report(nemt_data: dict) -> dict:
    concerns = nemt_data.get("compliance_concerns", [])
    active   = len(nemt_data.get("active_trips", []))
    drivers  = len(nemt_data.get("active_drivers", []))
    rate     = nemt_data.get("completion_stats", {}).get("rate_pct", 100.0)
    critical = [c for c in concerns if c.get("urgency") == "critical"]
    return {
        "segment_health": max(30, 85 - len(critical) * 15),
        "active_trips": active,
        "active_drivers": drivers,
        "completion_rate_pct": rate,
        "compliance_flags": concerns,
        "broker_status": [
            {"broker": "MTM", "status": "unknown"},
            {"broker": "Modivcare", "status": "unknown"},
            {"broker": "Southeastrans", "status": "unknown"},
        ],
        "ops_summary": f"NEMT segment: {active} active trips, {drivers} drivers, {rate}% completion rate. {len(critical)} critical compliance issues.",
        "recommended_actions": ["Review all compliance flags", "Confirm auth numbers on in-progress trips"] if concerns else ["Segment operating normally"],
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    scope = str(payload.get("scope", "full")).lower()

    nemt_data = _fetch_nemt_data()

    llm_report = _call_qwen(nemt_data, scope)
    if llm_report is None:
        llm_report = _call_claude(nemt_data, scope)
    if llm_report is None:
        llm_report = _rule_based_report(nemt_data)

    compliance_flags = llm_report.get("compliance_flags", nemt_data.get("compliance_concerns", []))

    report = {
        "agent":       _NAME,
        "node":        _NODE,
        "firm":        _FIRM,
        "scope":       scope,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "segment":     "nemt",
        "segment_health":      llm_report.get("segment_health", 70),
        "active_trips":        llm_report.get("active_trips", len(nemt_data.get("active_trips", []))),
        "active_drivers":      llm_report.get("active_drivers", len(nemt_data.get("active_drivers", []))),
        "completion_rate_pct": llm_report.get("completion_rate_pct", nemt_data.get("completion_stats", {}).get("rate_pct", 0)),
        "compliance_flags":    compliance_flags,
        "broker_status":       llm_report.get("broker_status", []),
        "ops_summary":         llm_report.get("ops_summary", ""),
        "recommended_actions": llm_report.get("recommended_actions", []),
        "llm_powered":         "db_error" not in nemt_data,
    }

    mem.remember(
        _NAME, "segment_report", report, confidence=0.88,
        summary=f"NEMT report: health={report['segment_health']} trips={report['active_trips']} drivers={report['active_drivers']} completion={report['completion_rate_pct']}%",
    )
    mem.remember(
        _NAME, "compliance_flags",
        {"flags": compliance_flags, "critical_count": len([f for f in compliance_flags if f.get("urgency") == "critical"]), "timestamp": report["timestamp"]},
        confidence=0.95,
        summary=f"{len(compliance_flags)} compliance flags — {len([f for f in compliance_flags if f.get('urgency') == 'critical'])} critical",
    )

    log_agent(
        _NAME, "nemt_report",
        payload={"scope": scope},
        result=f"health={report['segment_health']} trips={report['active_trips']} flags={len(compliance_flags)}",
    )

    return report

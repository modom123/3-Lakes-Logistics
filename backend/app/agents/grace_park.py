"""Grace Park — Rate Analyst · North America Trading Co.

Role: Rate Analyst for the North America Trading Co trading desk.
Mission: Calculate optimal carrier pay for each NATCO load to protect margin,
         flag thin spreads before coverage is committed, and track RPM benchmarks
         by lane and equipment type to inform Rex Sterling's trading decisions.

Payload keys:
  scope         str   "analyze" | "benchmarks" | "flag_thin"   default: "analyze"
  load_id       str   (for scope="analyze") analyze a specific load
  broker_pay    float (for scope="analyze") broker rate
  carrier_pay   float (for scope="analyze") proposed carrier rate
  miles         float (for scope="analyze") load miles
  equipment     str   (for scope="analyze") equipment type

Outputs (org memory):
  grace_park/rate_analysis   — per-load rate verdict
  grace_park/rpm_benchmarks  — current RPM benchmarks by equipment
  grace_park/thin_spreads    — loads where spread is below threshold
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem

_NAME = "grace_park"
_DIVISION = "North America Trading Co"

# Minimum spread thresholds by equipment (dollars)
SPREAD_MINIMUMS: dict[str, float] = {
    "Dry Van 53'": 200.0,
    "Dry Van 48'": 180.0,
    "Reefer": 250.0,
    "Flatbed": 200.0,
    "Step Deck": 200.0,
    "Cargo Van": 50.0,
    "26 Foot Box Truck": 100.0,
    "16 Foot Box Truck": 75.0,
    "Tanker / Hazmat": 300.0,
    "default": 200.0,
}

# Target spread (what we shoot for)
SPREAD_TARGETS: dict[str, float] = {
    "Dry Van 53'": 400.0,
    "Dry Van 48'": 350.0,
    "Reefer": 500.0,
    "Flatbed": 375.0,
    "Step Deck": 350.0,
    "Cargo Van": 150.0,
    "26 Foot Box Truck": 225.0,
    "16 Foot Box Truck": 175.0,
    "Tanker / Hazmat": 450.0,
    "default": 350.0,
}

# Typical market RPM ranges (broker pay) by equipment
RPM_BENCHMARKS: dict[str, dict[str, float]] = {
    "Dry Van 53'":     {"low": 2.10, "mid": 2.60, "high": 3.20},
    "Dry Van 48'":     {"low": 2.00, "mid": 2.50, "high": 3.10},
    "Reefer":          {"low": 2.50, "mid": 3.10, "high": 3.90},
    "Flatbed":         {"low": 2.30, "mid": 2.80, "high": 3.50},
    "Step Deck":       {"low": 2.20, "mid": 2.75, "high": 3.40},
    "Cargo Van":       {"low": 1.20, "mid": 1.60, "high": 2.10},
    "26 Foot Box Truck": {"low": 1.80, "mid": 2.20, "high": 2.80},
    "16 Foot Box Truck": {"low": 1.60, "mid": 2.00, "high": 2.50},
    "Tanker / Hazmat": {"low": 3.00, "mid": 3.80, "high": 4.80},
}


def analyze_load(broker_pay: float, carrier_pay: float | None,
                 miles: float | None, equipment: str) -> dict:
    """Core rate analysis for a single load."""
    spread = (broker_pay - carrier_pay) if carrier_pay else None
    broker_rpm = (broker_pay / miles) if miles else None
    carrier_rpm = (carrier_pay / miles) if (miles and carrier_pay) else None
    spread_rpm = (spread / miles) if (miles and spread is not None) else None

    min_spread = SPREAD_MINIMUMS.get(equipment, SPREAD_MINIMUMS["default"])
    target_spread = SPREAD_TARGETS.get(equipment, SPREAD_TARGETS["default"])
    bench = RPM_BENCHMARKS.get(equipment, RPM_BENCHMARKS.get("Dry Van 53'"))

    # Recommended max carrier pay (to hit target spread)
    rec_max_carrier_pay = broker_pay - target_spread
    rec_min_carrier_pay = broker_pay - (target_spread * 1.5)  # great spread

    # Verdict
    if spread is None:
        verdict = "pending"
        color = "blue"
        note = f"No carrier pay set. Recommend offering ${rec_max_carrier_pay:,.0f} (keeps ${target_spread:,.0f} spread)."
    elif spread < 0:
        verdict = "loss"
        color = "red"
        note = f"LOSING MONEY — carrier pay exceeds broker pay by ${abs(spread):,.0f}. Do not cover."
    elif spread < min_spread:
        verdict = "thin"
        color = "orange"
        note = f"Spread ${spread:,.0f} is below minimum ${min_spread:,.0f} for {equipment}. Renegotiate carrier rate to ≤${broker_pay - min_spread:,.0f}."
    elif spread < target_spread:
        verdict = "acceptable"
        color = "yellow"
        note = f"Spread ${spread:,.0f} is acceptable but below target ${target_spread:,.0f}. Good to cover."
    else:
        verdict = "strong"
        color = "green"
        note = f"Strong spread of ${spread:,.0f} ({((spread/broker_pay)*100):.1f}% margin). Cover immediately."

    # RPM context
    rpm_note = ""
    if broker_rpm and bench:
        if broker_rpm < bench["low"]:
            rpm_note = f"Broker RPM ${broker_rpm:.2f} is BELOW market low ${bench['low']:.2f}. Push back on rate."
        elif broker_rpm > bench["high"]:
            rpm_note = f"Broker RPM ${broker_rpm:.2f} is ABOVE market high — premium load, prioritize coverage."
        else:
            rpm_note = f"Broker RPM ${broker_rpm:.2f} is within normal market range (${bench['low']:.2f}–${bench['high']:.2f})."

    return {
        "verdict": verdict,
        "color": color,
        "spread": round(spread, 2) if spread is not None else None,
        "spread_pct": round((spread / broker_pay) * 100, 1) if spread and broker_pay else None,
        "broker_rpm": round(broker_rpm, 2) if broker_rpm else None,
        "carrier_rpm": round(carrier_rpm, 2) if carrier_rpm else None,
        "spread_rpm": round(spread_rpm, 2) if spread_rpm else None,
        "recommended_max_carrier_pay": round(rec_max_carrier_pay, 0),
        "recommended_floor_carrier_pay": round(max(rec_min_carrier_pay, broker_pay * 0.70), 0),
        "min_spread_threshold": min_spread,
        "target_spread": target_spread,
        "analysis_note": note,
        "rpm_context": rpm_note,
    }


def _scan_thin_spreads() -> list[dict]:
    """Scan all open NATCO loads for thin or missing spreads."""
    try:
        db = get_supabase()
        res = db.table("loads").select("*").order("created_at", desc=True).limit(200).execute()
        loads = [l for l in (res.data or []) if
                 l.get("load_number", "").startswith("NT-") or "[NATCO]" in (l.get("notes") or "")]
    except Exception:
        return []

    thin = []
    for l in loads:
        status = (l.get("status") or "").lower()
        if status in ("delivered", "completed", "closed"):
            continue
        broker_pay = float(l.get("rate") or l.get("rate_total") or 0)
        carrier_pay = float(l.get("carrier_pay") or 0)
        equip = l.get("equipment_type") or "Dry Van 53'"
        if not broker_pay:
            continue
        result = analyze_load(broker_pay, carrier_pay or None, None, equip)
        if result["verdict"] in ("thin", "loss", "pending"):
            thin.append({
                "load_number": l.get("load_number"),
                "route": f"{l.get('origin','?')} → {l.get('destination','?')}",
                "broker_pay": broker_pay,
                "carrier_pay": carrier_pay or None,
                "verdict": result["verdict"],
                "note": result["analysis_note"],
                "recommended_max_carrier_pay": result["recommended_max_carrier_pay"],
            })
    return thin


def run(payload: dict[str, Any]) -> dict[str, Any]:
    scope = payload.get("scope", "analyze")

    if scope == "analyze":
        broker_pay = float(payload.get("broker_pay") or 0)
        carrier_pay = float(payload.get("carrier_pay") or 0) or None
        miles = float(payload.get("miles") or 0) or None
        equipment = payload.get("equipment") or "Dry Van 53'"
        if not broker_pay:
            return {"agent": _NAME, "error": "broker_pay required for scope=analyze"}
        result = analyze_load(broker_pay, carrier_pay, miles, equipment)
        mem.write(_NAME, "rate_analysis", {**result, "analyzed_at": datetime.now(timezone.utc).isoformat()})
        log_agent(_NAME, "analyze", result=f"verdict={result['verdict']} spread={result.get('spread')}")
        return {"agent": _NAME, "division": _DIVISION, "analysis": result}

    elif scope == "flag_thin":
        thin = _scan_thin_spreads()
        mem.write(_NAME, "thin_spreads", thin)
        log_agent(_NAME, "flag_thin", result=f"{len(thin)} thin loads found")
        return {"agent": _NAME, "division": _DIVISION, "thin_spreads": thin, "count": len(thin)}

    else:  # benchmarks
        mem.write(_NAME, "rpm_benchmarks", RPM_BENCHMARKS)
        log_agent(_NAME, "benchmarks", result="served")
        return {"agent": _NAME, "division": _DIVISION, "benchmarks": RPM_BENCHMARKS, "spread_targets": SPREAD_TARGETS}

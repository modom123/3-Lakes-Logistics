"""Kai — Light Fleet Load Finder.

Sweeps load sources for each Light Fleet segment and surfaces available trips.
Each segment has different load sources — Kai knows them all.

Actions:
  sweep            scan all segments for available loads → return list
  sweep_segment    scan one segment (nemt | medical_courier | executive | courier | gig_fleet)
  queue_trip       manually queue a found trip into light_vehicle_trips
  status           last sweep summary from memory
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from . import memory as mem

_NAME = "kai"

# ── Load source registry ──────────────────────────────────────────────────────
# Each entry describes WHERE loads come from and HOW to find them.
# Real integrations are stubs — wired when broker API keys are configured.

LOAD_SOURCES = {
    "nemt": {
        "label": "NEMT Medical Transport",
        "sources": [
            "MTM (Medical Transportation Management) — API partner",
            "Modivcare (formerly LogistiCare) — contractor portal",
            "Southeastrans — dispatch feed",
            "Local hospital discharge coordinators — outbound calls",
            "State Medicaid NEMT broker contracts",
        ],
        "find_loads": "_find_nemt_loads",
    },
    "medical_courier": {
        "label": "Medical Courier",
        "sources": [
            "Hospital lab specimen pickup contracts",
            "Pharmacy last-mile delivery partners",
            "Blood bank & specimen transport networks",
            "Outpatient clinic supply runs",
        ],
        "find_loads": "_find_medical_courier_loads",
    },
    "executive": {
        "label": "Executive & Black Car",
        "sources": [
            "Corporate executive_accounts table — direct clients",
            "Airport transfer booking platforms (GroundLink API)",
            "Event management companies — outbound sales",
            "Hotel concierge partnerships",
        ],
        "find_loads": "_find_executive_loads",
    },
    "courier": {
        "label": "Same-Day Courier",
        "sources": [
            "GoShip same-day API",
            "Curri last-mile platform",
            "FedEx Custom Critical subcontract",
            "Local e-commerce merchant contracts",
            "Restaurant / catering delivery overflow",
        ],
        "find_loads": "_find_courier_loads",
    },
    "gig_fleet": {
        "label": "Gig Fleet Management",
        "sources": [
            "Owner-operator fleet enrollment (direct)",
            "Rideshare overflow demand — surge period fills",
            "Airport lot holding & staging management",
            "Multi-vehicle owner dispatch consolidation",
        ],
        "find_loads": "_find_gig_fleet_loads",
    },
}


def _db():
    try:
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Segment sweep stubs ───────────────────────────────────────────────────────
# These stubs return the shape of a found load. In production, replace with
# real API calls to each broker / platform.

def _find_nemt_loads(limit: int = 10) -> list[dict]:
    sb = _db()
    pending: list[dict] = []
    if sb:
        try:
            rows = (
                sb.table("nemt_clients")
                .select("id,full_name,phone,pickup_address,dropoff_address,preferred_pickup_time,insurance_provider,insurance_auth_number")
                .eq("status", "pending_trip")
                .limit(limit)
                .execute()
                .data or []
            )
            for r in rows:
                pending.append({
                    "segment": "nemt",
                    "source": "nemt_clients_table",
                    "passenger_name": r.get("full_name"),
                    "passenger_phone": r.get("phone"),
                    "pickup_address": r.get("pickup_address"),
                    "dropoff_address": r.get("dropoff_address"),
                    "scheduled_at": r.get("preferred_pickup_time"),
                    "insurance_provider": r.get("insurance_provider"),
                    "insurance_auth_number": r.get("insurance_auth_number"),
                    "nemt_client_id": r.get("id"),
                })
        except Exception:  # noqa: BLE001
            pass
    return pending


def _find_medical_courier_loads(limit: int = 10) -> list[dict]:
    return []


def _find_executive_loads(limit: int = 10) -> list[dict]:
    sb = _db()
    pending: list[dict] = []
    if sb:
        try:
            rows = (
                sb.table("executive_accounts")
                .select("id,company_name,contact_name,contact_phone,pickup_address,dropoff_address,scheduled_at")
                .eq("status", "trip_requested")
                .limit(limit)
                .execute()
                .data or []
            )
            for r in rows:
                pending.append({
                    "segment": "executive",
                    "source": "executive_accounts_table",
                    "passenger_name": r.get("contact_name"),
                    "passenger_phone": r.get("contact_phone"),
                    "pickup_address": r.get("pickup_address"),
                    "dropoff_address": r.get("dropoff_address"),
                    "scheduled_at": r.get("scheduled_at"),
                    "executive_account_id": r.get("id"),
                    "company_name": r.get("company_name"),
                })
        except Exception:  # noqa: BLE001
            pass
    return pending


def _find_courier_loads(limit: int = 10) -> list[dict]:
    return []


def _find_gig_fleet_loads(limit: int = 10) -> list[dict]:
    return []


_FINDERS = {
    "nemt": _find_nemt_loads,
    "medical_courier": _find_medical_courier_loads,
    "executive": _find_executive_loads,
    "courier": _find_courier_loads,
    "gig_fleet": _find_gig_fleet_loads,
}


def sweep_segment(segment: str, limit: int = 10) -> dict[str, Any]:
    if segment not in LOAD_SOURCES:
        return {"segment": segment, "error": f"unknown segment — valid: {list(LOAD_SOURCES)}"}
    loads = _FINDERS[segment](limit)
    log_agent(_NAME, f"sweep_{segment}", result=f"{len(loads)} loads found")
    return {
        "segment": segment,
        "label": LOAD_SOURCES[segment]["label"],
        "loads_found": len(loads),
        "loads": loads,
        "sources": LOAD_SOURCES[segment]["sources"],
    }


def sweep_all(limit_per_segment: int = 10) -> dict[str, Any]:
    results = {}
    total = 0
    for seg in LOAD_SOURCES:
        r = sweep_segment(seg, limit_per_segment)
        results[seg] = r
        total += r.get("loads_found", 0)
    mem.remember(
        _NAME, "last_sweep",
        {"total_loads": total, "swept_at": _now(), "segments": list(results.keys())},
        confidence=0.85,
        summary=f"Sweep complete: {total} loads across {len(results)} segments",
    )
    log_agent(_NAME, "sweep_all", result=f"total={total}")
    return {"swept_at": _now(), "total_loads": total, "segments": results}


def queue_trip(load: dict[str, Any]) -> dict[str, Any]:
    sb = _db()
    if not sb:
        return {"queued": False, "error": "db_unavailable"}
    try:
        row = {
            "trip_type": load.get("segment", "gig"),
            "passenger_name": load.get("passenger_name"),
            "passenger_phone": load.get("passenger_phone"),
            "pickup_address": load.get("pickup_address"),
            "dropoff_address": load.get("dropoff_address"),
            "scheduled_at": load.get("scheduled_at"),
            "insurance_provider": load.get("insurance_provider"),
            "insurance_auth_number": load.get("insurance_auth_number"),
            "status": "pending",
            "source": load.get("source", "kai_sweep"),
        }
        result = sb.table("light_vehicle_trips").insert(row).execute()
        trip_id = (result.data[0] or {}).get("id") if result.data else None
        log_agent(_NAME, "queue_trip", result=f"trip_id={trip_id} segment={row['trip_type']}")
        return {"queued": True, "trip_id": str(trip_id) if trip_id else None}
    except Exception as e:  # noqa: BLE001
        return {"queued": False, "error": str(e)}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "status")).lower()

    if action == "sweep":
        result = sweep_all(int(payload.get("limit", 10)))
        return {"agent": _NAME, **result}

    if action == "sweep_segment":
        seg = str(payload.get("segment", "")).lower()
        result = sweep_segment(seg, int(payload.get("limit", 10)))
        return {"agent": _NAME, **result}

    if action == "queue_trip":
        result = queue_trip(payload.get("load") or payload)
        return {"agent": _NAME, **result}

    if action == "status":
        last = mem.recall(_NAME, "last_sweep") or {}
        return {
            "agent": _NAME,
            "action": "status",
            "segments": list(LOAD_SOURCES.keys()),
            "last_sweep": last,
            "source_map": {k: v["sources"] for k, v in LOAD_SOURCES.items()},
        }

    return {"agent": _NAME, "error": f"unknown action: {action}"}

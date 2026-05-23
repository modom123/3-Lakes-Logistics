"""Carrier Brain — per-carrier relationship intelligence.

Where NEXUS stores aggregate patterns ("at_risk_count=5"),
Carrier Brain stores per-entity memory: what we know about
Blue Ridge Trucking specifically — their risk history, every
call Vance made, how many loads they've run, last campaign touch.

API:
    remember_carrier(carrier_id, name, memory_type, value, ...)
    recall_carrier(carrier_id, memory_type)
    recall_carrier_all(carrier_id)
    get_carrier_intelligence(carrier_id)
    search_by_type(memory_type, limit)   — e.g. all at-risk carriers
"""
from __future__ import annotations

from typing import Any

from ..logging_service import get_logger
from ..supabase_client import get_supabase

log = get_logger("carrier.brain")

# Recognised memory types — open-ended but these are canonical
MEMORY_TYPES = {
    "risk_profile",    # Winston: inactivity, load count, risk reason
    "call_history",    # Vance: total calls, connect rate, last status
    "load_pattern",    # derived: load count, avg rate, preferred lanes
    "relationship",    # Isabella: campaign touches, last message
    "onboarding",      # system/manual: onboarding step, blockers
}


# ── Write ─────────────────────────────────────────────────────────────────────

def remember_carrier(
    carrier_id: str,
    carrier_name: str | None,
    memory_type: str,
    value: Any,
    *,
    agent: str,
    confidence: float = 0.5,
    summary: str | None = None,
) -> None:
    """Upsert a carrier memory. Confidence reinforces on repeat writes.
    Never raises — must not crash business logic.
    """
    try:
        sb = get_supabase()
        existing = (
            sb.table("carrier_brain")
            .select("id,confidence,interaction_count")
            .eq("carrier_id", carrier_id)
            .eq("memory_type", memory_type)
            .limit(1)
            .execute()
        )
        mem_val = value if isinstance(value, (dict, list)) else {"value": value}

        if existing.data:
            old_conf = float(existing.data[0].get("confidence") or 0.5)
            old_count = int(existing.data[0].get("interaction_count") or 1)
            new_conf = min(1.0, old_conf + (1 - old_conf) * 0.15)
            (
                sb.table("carrier_brain")
                .update({
                    "memory_value":      mem_val,
                    "confidence":        round(new_conf, 3),
                    "interaction_count": old_count + 1,
                    "last_agent":        agent,
                    "summary":           summary,
                    "carrier_name":      carrier_name,
                    "updated_at":        "now()",
                })
                .eq("carrier_id", carrier_id)
                .eq("memory_type", memory_type)
                .execute()
            )
        else:
            sb.table("carrier_brain").insert({
                "carrier_id":      carrier_id,
                "carrier_name":    carrier_name,
                "memory_type":     memory_type,
                "memory_value":    mem_val,
                "confidence":      round(max(0.0, min(1.0, confidence)), 3),
                "last_agent":      agent,
                "interaction_count": 1,
                "summary":         summary,
            }).execute()

        log.debug("carrier brain write: %s/%s agent=%s", carrier_id, memory_type, agent)
    except Exception as e:  # noqa: BLE001
        log.warning("carrier brain write failed (%s/%s): %s", carrier_id, memory_type, e)


# ── Read ──────────────────────────────────────────────────────────────────────

def recall_carrier(carrier_id: str, memory_type: str) -> dict[str, Any] | None:
    try:
        res = (
            get_supabase().table("carrier_brain")
            .select("carrier_id,carrier_name,memory_type,memory_value,confidence,last_agent,interaction_count,summary,updated_at")
            .eq("carrier_id", carrier_id)
            .eq("memory_type", memory_type)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:  # noqa: BLE001
        log.warning("carrier brain recall failed (%s/%s): %s", carrier_id, memory_type, e)
        return None


def recall_carrier_all(carrier_id: str) -> list[dict[str, Any]]:
    """All memories for one carrier, highest confidence first."""
    try:
        res = (
            get_supabase().table("carrier_brain")
            .select("carrier_id,carrier_name,memory_type,memory_value,confidence,last_agent,interaction_count,summary,updated_at")
            .eq("carrier_id", carrier_id)
            .order("confidence", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as e:  # noqa: BLE001
        log.warning("carrier brain recall_all failed (%s): %s", carrier_id, e)
        return []


def recall_value(carrier_id: str, memory_type: str, default: Any = None) -> Any:
    mem = recall_carrier(carrier_id, memory_type)
    return mem["memory_value"] if mem else default


def search_by_type(memory_type: str, limit: int = 50) -> list[dict[str, Any]]:
    """All carriers that have a given memory type — e.g. all with risk_profile."""
    try:
        res = (
            get_supabase().table("carrier_brain")
            .select("carrier_id,carrier_name,memory_type,memory_value,confidence,last_agent,summary,updated_at")
            .eq("memory_type", memory_type)
            .order("confidence", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as e:  # noqa: BLE001
        log.warning("carrier brain search_by_type failed (%s): %s", memory_type, e)
        return []


def get_carrier_intelligence(carrier_id: str) -> dict[str, Any]:
    """Full carrier profile from the brain — all memory types assembled."""
    memories = recall_carrier_all(carrier_id)
    by_type = {m["memory_type"]: m for m in memories}
    name = memories[0]["carrier_name"] if memories else carrier_id
    return {
        "carrier_id":   carrier_id,
        "carrier_name": name,
        "memory_count": len(memories),
        "risk_profile": by_type.get("risk_profile", {}).get("memory_value"),
        "call_history": by_type.get("call_history", {}).get("memory_value"),
        "load_pattern": by_type.get("load_pattern", {}).get("memory_value"),
        "relationship": by_type.get("relationship", {}).get("memory_value"),
        "onboarding":   by_type.get("onboarding",   {}).get("memory_value"),
        "memories":     memories,
    }


def get_at_risk_carriers(limit: int = 25) -> list[dict[str, Any]]:
    """All carriers with a risk_profile memory, sorted by confidence (risk certainty)."""
    rows = search_by_type("risk_profile", limit=limit)
    result = []
    for r in rows:
        mv = r.get("memory_value") or {}
        result.append({
            "carrier_id":   r["carrier_id"],
            "carrier_name": r.get("carrier_name"),
            "priority":     mv.get("priority", "unknown"),
            "risk_reason":  mv.get("risk_reason"),
            "last_load_at": mv.get("last_load_at"),
            "total_loads":  mv.get("total_loads", 0),
            "confidence":   r.get("confidence", 0),
            "flagged_by":   r.get("last_agent"),
            "summary":      r.get("summary"),
            "updated_at":   r.get("updated_at"),
        })
    result.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x["priority"], 3))
    return result

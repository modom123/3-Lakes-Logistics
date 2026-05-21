"""Org Brain — Agent Memory Module.

Every AI agent reads from and writes to this shared memory layer so
the organization learns from each interaction rather than starting
fresh on every run.

Core API:
    remember(agent, key, value)    — persist or reinforce a memory
    recall(agent, key)             — read a specific memory
    recall_all(agent)              — all memories for one agent
    recall_org()                   — shared org-level intelligence
    log_interaction(...)           — log a cross-agent knowledge exchange

Confidence model:
    New memory:      starts at provided confidence (default 0.5)
    Reinforcement:   conf = min(1.0, old + (1 - old) * 0.15)
    Decay not implemented yet — all memories persist until overwritten
"""
from __future__ import annotations

from typing import Any

from ..logging_service import get_logger
from ..supabase_client import get_supabase

log = get_logger("org.brain")

_INTERACTION_MAX_ROWS = 500
_INTERACTION_MAX_DAYS = 30


# ── Write ─────────────────────────────────────────────────────────────────────

def remember(
    agent_name: str,
    key: str,
    value: Any,
    *,
    confidence: float = 0.5,
    source_agent: str | None = None,
    summary: str | None = None,
) -> None:
    """Upsert a memory. If it already exists, reinforce confidence and update value.
    Never raises — memory writes must not crash business logic.
    """
    try:
        sb = get_supabase()

        # Check if memory already exists to calculate reinforced confidence
        existing = (
            sb.table("agent_memory")
            .select("id,confidence,interaction_count")
            .eq("agent_name", agent_name)
            .eq("memory_key", key)
            .limit(1)
            .execute()
        )

        if existing.data:
            old_conf = float(existing.data[0].get("confidence") or 0.5)
            old_count = int(existing.data[0].get("interaction_count") or 1)
            # Asymptotic confidence growth — never reaches 1.0 but approaches it
            new_conf = min(1.0, old_conf + (1 - old_conf) * 0.15)
            (
                sb.table("agent_memory")
                .update({
                    "memory_value":      value if isinstance(value, (dict, list)) else {"value": value},
                    "confidence":        round(new_conf, 3),
                    "interaction_count": old_count + 1,
                    "source_agent":      source_agent or agent_name,
                    "summary":           summary,
                    "updated_at":        "now()",
                })
                .eq("agent_name", agent_name)
                .eq("memory_key", key)
                .execute()
            )
            log.debug("memory reinforced: %s/%s conf=%.2f→%.2f", agent_name, key, old_conf, new_conf)
        else:
            mem_val = value if isinstance(value, (dict, list)) else {"value": value}
            sb.table("agent_memory").insert({
                "agent_name":      agent_name,
                "memory_key":      key,
                "memory_value":    mem_val,
                "confidence":      round(max(0.0, min(1.0, confidence)), 3),
                "source_agent":    source_agent or agent_name,
                "interaction_count": 1,
                "summary":         summary,
            }).execute()
            log.debug("memory created: %s/%s conf=%.2f", agent_name, key, confidence)

    except Exception as e:  # noqa: BLE001
        log.warning("memory write failed (%s/%s): %s", agent_name, key, e)


# ── Read ──────────────────────────────────────────────────────────────────────

def recall(agent_name: str, key: str) -> dict[str, Any] | None:
    """Retrieve a specific memory. Returns None if not found or on error."""
    try:
        sb = get_supabase()
        res = (
            sb.table("agent_memory")
            .select("memory_key,memory_value,confidence,interaction_count,source_agent,updated_at,summary")
            .eq("agent_name", agent_name)
            .eq("memory_key", key)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:  # noqa: BLE001
        log.warning("memory recall failed (%s/%s): %s", agent_name, key, e)
        return None


def recall_all(agent_name: str) -> list[dict[str, Any]]:
    """All memories for one agent, ordered by confidence desc."""
    try:
        sb = get_supabase()
        res = (
            sb.table("agent_memory")
            .select("memory_key,memory_value,confidence,interaction_count,source_agent,updated_at,summary")
            .eq("agent_name", agent_name)
            .order("confidence", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as e:  # noqa: BLE001
        log.warning("recall_all failed (%s): %s", agent_name, e)
        return []


def recall_org() -> list[dict[str, Any]]:
    """All shared org-level memories — readable by any agent."""
    return recall_all("org")


def recall_value(agent_name: str, key: str, default: Any = None) -> Any:
    """Convenience: return just the memory_value dict, or default."""
    mem = recall(agent_name, key)
    if mem:
        return mem.get("memory_value", default)
    return default


# ── Log interactions ──────────────────────────────────────────────────────────

def log_interaction(
    from_agent: str,
    to_agent: str,
    interaction_type: str,
    *,
    payload: dict | None = None,
    result: dict | None = None,
    outcome: str = "success",
    outcome_notes: str | None = None,
) -> None:
    """Log a cross-agent knowledge exchange. Never raises."""
    try:
        get_supabase().table("agent_interactions").insert({
            "from_agent":        from_agent,
            "to_agent":          to_agent,
            "interaction_type":  interaction_type,
            "payload":           payload or {},
            "result":            result or {},
            "outcome":           outcome,
            "outcome_notes":     outcome_notes,
        }).execute()
        log.debug("interaction logged: %s→%s [%s]", from_agent, to_agent, interaction_type)
    except Exception as e:  # noqa: BLE001
        log.warning("interaction log failed (%s→%s): %s", from_agent, to_agent, e)


def prune_interactions(
    max_rows: int = _INTERACTION_MAX_ROWS,
    max_days: int = _INTERACTION_MAX_DAYS,
) -> dict[str, Any]:
    """Delete old agent_interactions to keep the table lean.

    Runs daily via APScheduler. Also callable from the API by Commander.
    Two-pass strategy:
      1. Delete everything older than max_days
      2. If still over max_rows, delete oldest until under limit
    agent_memory is never pruned here — it's UPSERT-based (1 row per key).
    """
    from datetime import datetime, timedelta, timezone

    deleted_age = 0
    deleted_overflow = 0
    try:
        sb = get_supabase()

        # Pass 1: age-based pruning
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_days)).isoformat()
        age_res = sb.table("agent_interactions").delete().lt("created_at", cutoff).execute()
        deleted_age = len(age_res.data or [])

        # Pass 2: row-count cap — find the (max_rows+1)th most recent row and
        # delete everything at or before that timestamp
        boundary = (
            sb.table("agent_interactions")
            .select("created_at")
            .order("created_at", desc=True)
            .range(max_rows, max_rows)
            .execute()
            .data
        )
        if boundary:
            boundary_ts = boundary[0]["created_at"]
            overflow_res = (
                sb.table("agent_interactions")
                .delete()
                .lte("created_at", boundary_ts)
                .execute()
            )
            deleted_overflow = len(overflow_res.data or [])

        total = deleted_age + deleted_overflow
        log.info("interaction prune complete: %d removed (%d age, %d overflow)", total, deleted_age, deleted_overflow)
        return {"deleted_by_age": deleted_age, "deleted_by_overflow": deleted_overflow, "total_deleted": total}
    except Exception as e:  # noqa: BLE001
        log.warning("interaction prune failed: %s", e)
        return {"deleted_by_age": 0, "deleted_by_overflow": 0, "total_deleted": 0, "error": str(e)}


# ── Org-wide read helper for Victoria ────────────────────────────────────────

def read_org_intelligence() -> dict[str, Any]:
    """Pull all agent memories + recent interactions for strategic assessment.
    Used by Victoria to build her full-org snapshot.
    """
    try:
        sb = get_supabase()

        # All memories across all agents
        all_memories_res = (
            sb.table("agent_memory")
            .select("agent_name,memory_key,memory_value,confidence,interaction_count,updated_at,summary")
            .order("confidence", desc=True)
            .execute()
        )
        all_memories: list[dict] = all_memories_res.data or []

        # Recent interactions (last 50)
        interactions_res = (
            sb.table("agent_interactions")
            .select("from_agent,to_agent,interaction_type,outcome,outcome_notes,created_at")
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        interactions: list[dict] = interactions_res.data or []

        # Group memories by agent
        by_agent: dict[str, list] = {}
        for mem in all_memories:
            agent = mem["agent_name"]
            by_agent.setdefault(agent, []).append(mem)

        return {
            "total_memories": len(all_memories),
            "agents_with_memory": len(by_agent),
            "recent_interactions": len(interactions),
            "by_agent": by_agent,
            "interactions": interactions[:20],
        }
    except Exception as e:  # noqa: BLE001
        log.warning("read_org_intelligence failed: %s", e)
        return {"total_memories": 0, "agents_with_memory": 0, "recent_interactions": 0, "by_agent": {}, "interactions": []}

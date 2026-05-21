"""Org Brain API — exposes agent memory and interaction log to Eagle Eye.

GET  /api/org/brain           — full intelligence snapshot (all agents)
GET  /api/org/brain/{agent}   — single agent's memories
GET  /api/org/interactions    — recent cross-agent interaction feed
DELETE /api/org/brain/{agent}/{key} — clear a specific memory (Commander only)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..agents import memory as mem
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.get("/org/brain")
def org_brain() -> dict:
    """Full org intelligence snapshot — all agent memories + interaction feed."""
    intel = mem.read_org_intelligence()
    return {"ok": True, **intel}


@router.get("/org/brain/{agent_name}")
def agent_brain(agent_name: str) -> dict:
    """All memories for a single agent."""
    memories = mem.recall_all(agent_name)
    return {
        "ok": True,
        "agent": agent_name,
        "memory_count": len(memories),
        "memories": memories,
    }


@router.get("/org/interactions")
def interaction_feed(limit: int = 50) -> dict:
    """Recent cross-agent interaction log."""
    from ..supabase_client import get_supabase
    try:
        res = (
            get_supabase().table("agent_interactions")
            .select("*")
            .order("created_at", desc=True)
            .limit(min(limit, 200))
            .execute()
        )
        return {"ok": True, "count": len(res.data or []), "interactions": res.data or []}
    except Exception as e:
        raise HTTPException(502, f"Could not fetch interactions: {e}")


@router.delete("/org/brain/{agent_name}/{memory_key}")
def clear_memory(agent_name: str, memory_key: str) -> dict:
    """Commander can clear a specific memory to force a fresh re-learn."""
    from ..supabase_client import get_supabase
    try:
        get_supabase().table("agent_memory").delete().eq("agent_name", agent_name).eq("memory_key", memory_key).execute()
        return {"ok": True, "cleared": f"{agent_name}/{memory_key}"}
    except Exception as e:
        raise HTTPException(502, f"Could not clear memory: {e}")


@router.post("/org/brain/prune")
def prune_interaction_log(max_rows: int = 500, max_days: int = 30) -> dict:
    """Commander: manually trim the interaction log.
    Runs automatically every day at 05:30 UTC — this is for on-demand cleanup.
    agent_memory (the actual learning) is never deleted by this endpoint.
    """
    from ..agents.memory import prune_interactions
    result = prune_interactions(max_rows=max_rows, max_days=max_days)
    return {"ok": True, **result}

"""Agent control surface — the command center's buttons that manually
trigger specific AI-agent actions. Routes delegate to app/agents/*.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..agents import router as agent_router
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.get("/list")
def list_agents() -> dict:
    return {"agents": agent_router.available_agents()}


@router.post("/{agent}/run")
def run_agent(agent: str, payload: dict | None = None) -> dict:
    if not agent_router.has(agent):
        raise HTTPException(404, f"unknown agent: {agent}")
    return agent_router.dispatch(agent, payload or {})


@router.get("/log")
def recent_agent_log(agent: str | None = None, limit: int = 100) -> dict:
    from ..supabase_client import get_supabase
    q = get_supabase().table("agent_log").select("*").order("ts", desc=True).limit(limit)
    if agent:
        q = q.eq("agent", agent)
    return {"items": q.execute().data or []}

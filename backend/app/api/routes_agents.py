"""Agent control surface — the EAGLE EYE's buttons that manually
trigger specific AI-agent actions. Routes delegate to app/agents/*.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..agents import router as agent_router
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


class ToggleBody(BaseModel):
    enabled: bool


@router.get("/list")
def list_agents() -> dict:
    return {"agents": agent_router.available_agents()}


@router.get("/toggles")
def list_agent_toggles() -> dict:
    """Return the enabled/disabled state for every registered agent."""
    from ..agents.toggles import get_all_toggles
    names = agent_router.available_agents()
    return {"toggles": get_all_toggles(names)}


@router.post("/{agent}/toggle")
def set_agent_toggle(agent: str, body: ToggleBody) -> dict:
    """Enable or disable an agent. Affects both scheduled and manual runs."""
    if not agent_router.has(agent):
        raise HTTPException(404, f"unknown agent: {agent}")
    from ..agents.toggles import set_enabled
    set_enabled(agent, body.enabled)
    return {"agent": agent, "enabled": body.enabled}


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

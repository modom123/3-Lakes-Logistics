"""Agent control surface — the EAGLE EYE's buttons that manually
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


@router.post("/directive")
def send_directive(body: dict) -> dict:
    """Store a commander directive in an agent's memory so it's applied on the
    agent's next run. Used by the executive offices ("Send Directive" /
    "Broadcast to CC Gulley"). Body: {agent, subject?, message}.
    """
    from datetime import datetime, timezone
    from ..agents import memory as mem

    agent = (body.get("agent") or "").strip()
    message = (body.get("message") or "").strip()
    subject = (body.get("subject") or "Commander Directive").strip()
    if not agent:
        raise HTTPException(400, "agent is required")
    if not message:
        raise HTTPException(400, "message is required")

    ts = datetime.now(timezone.utc).isoformat()
    directive = {"subject": subject, "message": message, "issued_at": ts, "from": "commander"}
    # Latest directive (read by the agent on next run) + a timestamped copy for history.
    mem.remember(agent, "commander_directive", directive, confidence=0.95,
                 source_agent="commander", summary=subject)
    mem.remember(agent, f"directive:{ts}", directive, confidence=0.9,
                 source_agent="commander", summary=subject)
    return {"ok": True, "agent": agent, "subject": subject, "issued_at": ts}


@router.get("/log")
def recent_agent_log(agent: str | None = None, limit: int = 100) -> dict:
    from ..supabase_client import get_supabase
    q = get_supabase().table("agent_log").select("*").order("ts", desc=True).limit(limit)
    if agent:
        q = q.eq("agent", agent)
    return {"items": q.execute().data or []}

"""Agent router + task queue coordinator (Stage 5 step 61).

`dispatch()` — invoke an agent synchronously (used by `/api/agents/{agent}/run`).
`enqueue()`  — persist a task into `agent_tasks` for Vance's worker loop.
`claim_next()` — atomic pull of the next ready task (FOR UPDATE SKIP LOCKED
would be ideal; we simulate with `status='claimed'` guarded update).
`finalize()` — write result + an `agent_runs` audit row.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from ..logging_service import log_agent
from . import (
    atlas, audit, beacon, echo, nova, orbit, penny, pulse,
    scout, settler, shield, signal, sonny, vance,
)

_DISPATCH: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "vance":   vance.run,
    "sonny":   sonny.run,
    "shield":  shield.run,
    "scout":   scout.run,
    "penny":   penny.run,
    "settler": settler.run,
    "audit":   audit.run,
    "nova":    nova.run,
    "signal":  signal.run,
    "echo":    echo.run,
    "atlas":   atlas.run,
    "beacon":  beacon.run,
    "orbit":   orbit.run,
    "pulse":   pulse.run,
}


def available_agents() -> list[str]:
    return sorted(_DISPATCH.keys())


def has(agent: str) -> bool:
    return agent in _DISPATCH


def dispatch(agent: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Synchronous dispatch with automatic audit row."""
    if agent not in _DISPATCH:
        return {"status": "error", "error": f"unknown agent {agent}"}
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        result = _DISPATCH[agent](payload)
        status = str(result.get("status", "ok"))
        error = None
    except Exception as exc:  # noqa: BLE001
        result = {"status": "error", "error": str(exc)}
        status = "error"
        error = str(exc)
    duration_ms = int((time.perf_counter() - started) * 1000)
    _write_run(
        agent=agent, kind=str(payload.get("kind") or "run"),
        status=status, started_at=started_at, duration_ms=duration_ms,
        input=payload, output=result, error=error, task_id=payload.get("_task_id"),
    )
    return result


def enqueue(
    agent: str,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    priority: int = 5,
    carrier_id: str | None = None,
    run_at: str | None = None,
) -> str | None:
    """Push a job onto agent_tasks. Returns task id (or None if offline)."""
    if agent not in _DISPATCH:
        raise ValueError(f"unknown agent {agent}")
    try:
        from ..supabase_client import get_supabase
        row = {
            "agent": agent, "kind": kind, "payload": payload or {},
            "priority": priority, "carrier_id": carrier_id,
            "run_at": run_at or datetime.now(timezone.utc).isoformat(),
        }
        res = get_supabase().table("agent_tasks").insert(row).execute()
        return (res.data or [{}])[0].get("id")
    except Exception as exc:  # noqa: BLE001
        log_agent(agent, "enqueue_failed", payload=payload, error=str(exc))
        return None


def claim_next() -> dict | None:
    """Return the next ready task, flipped to `claimed`. None if empty."""
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        now_iso = datetime.now(timezone.utc).isoformat()
        rows = (
            sb.table("agent_tasks")
            .select("*")
            .eq("status", "pending")
            .lte("run_at", now_iso)
            .order("priority")
            .order("run_at")
            .limit(1)
            .execute()
        ).data or []
        if not rows:
            return None
        task = rows[0]
        upd = (
            sb.table("agent_tasks")
            .update({"status": "claimed", "claimed_at": now_iso})
            .eq("id", task["id"]).eq("status", "pending")
            .execute()
        )
        if not (upd.data or []):
            return None  # lost the race
        return task
    except Exception as exc:  # noqa: BLE001
        log_agent("vance", "claim_failed", error=str(exc))
        return None


def finalize(task: dict, result: dict, error: str | None = None) -> None:
    """Close out a task: write status + result into agent_tasks."""
    status = "error" if error else str(result.get("status") or "done")
    if status == "error" and (task.get("attempts") or 0) + 1 < (task.get("max_attempts") or 3):
        status = "pending"  # retry
    try:
        from ..supabase_client import get_supabase
        get_supabase().table("agent_tasks").update({
            "status": status,
            "attempts": (task.get("attempts") or 0) + 1,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
            "error": error,
        }).eq("id", task["id"]).execute()
    except Exception as exc:  # noqa: BLE001
        log_agent(task.get("agent") or "unknown", "finalize_failed", error=str(exc))


def _write_run(
    *, agent: str, kind: str, status: str, started_at: str, duration_ms: int,
    input: dict, output: dict, error: str | None, task_id: str | None,
) -> None:
    try:
        from ..supabase_client import get_supabase
        get_supabase().table("agent_runs").insert({
            "task_id": task_id,
            "agent": agent,
            "kind": kind,
            "status": status,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
            "input": input,
            "output": output,
            "error": error,
        }).execute()
    except Exception as exc:  # noqa: BLE001
        log_agent(agent, "run_audit_failed", error=str(exc))

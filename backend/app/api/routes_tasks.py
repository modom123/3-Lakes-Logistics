"""CEO task list — server persistence for the "Todo → CC Gulley" tab.

Backs the executive-office todo list so tasks survive across browsers and
devices instead of living only in the browser's localStorage. Also feeds the
assigned agent's NEXUS memory so the tasks are visible to the agent on its
next run, not just as a one-shot broadcast.

Requires table `ceo_tasks` (see backend/sql/021_ceo_tasks.sql). If the table
is absent the frontend falls back to localStorage, so these endpoints fail
loudly rather than silently corrupting state.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])

# Map DB columns → the field names the Eagle Eye frontend uses (kept identical
# to the legacy localStorage shape so the UI needs no per-field translation).
_PRIORITIES = {"high", "med", "low"}


def _to_client(row: dict) -> dict:
    """Shape a ceo_tasks row into the frontend task object."""
    return {
        "id": row.get("id"),
        "title": row.get("title") or "",
        "desc": row.get("description") or "",
        "due": row.get("due_date") or "",
        "pri": row.get("priority") or "med",
        "cat": row.get("category") or "strategy",
        "done": bool(row.get("done")),
        "owner": row.get("owner") or "mark",
        "assigned_to": row.get("assigned_to") or "cc_gulley",
        "created": row.get("created_at"),
    }


def _from_client(body: dict) -> dict:
    """Shape an incoming frontend task object into ceo_tasks columns.

    Accepts both the frontend keys (desc/due/pri/cat) and raw column names so
    callers can use either.
    """
    out: dict = {}
    if "title" in body:
        out["title"] = (body.get("title") or "").strip()
    if "desc" in body or "description" in body:
        out["description"] = (body.get("desc") or body.get("description") or "").strip()
    if "due" in body or "due_date" in body:
        out["due_date"] = (body.get("due") or body.get("due_date")) or None
    if "pri" in body or "priority" in body:
        pri = (body.get("pri") or body.get("priority") or "med").strip().lower()
        out["priority"] = pri if pri in _PRIORITIES else "med"
    if "cat" in body or "category" in body:
        out["category"] = (body.get("cat") or body.get("category") or "strategy").strip()
    if "owner" in body:
        out["owner"] = (body.get("owner") or "mark").strip()
    if "assigned_to" in body:
        out["assigned_to"] = (body.get("assigned_to") or "cc_gulley").strip()
    if "done" in body:
        out["done"] = bool(body.get("done"))
        out["completed_at"] = (
            datetime.now(timezone.utc).isoformat() if body.get("done") else None
        )
    return out


@router.get("/")
def list_tasks(owner: str = "mark", include_done: bool = True, limit: int = 500) -> dict:
    sb = get_supabase()
    q = sb.table("ceo_tasks").select("*").eq("owner", owner)
    if not include_done:
        q = q.eq("done", False)
    # Open tasks first, then by due date, newest created last.
    q = q.order("done").order("due_date").order("created_at", desc=True).limit(limit)
    try:
        res = q.execute()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Database error loading tasks: {exc}") from exc
    return {"items": [_to_client(r) for r in (res.data or [])]}


@router.post("/")
def create_task(body: dict) -> dict:
    data = _from_client(body)
    if not data.get("title"):
        raise HTTPException(400, "title is required")
    data.setdefault("owner", "mark")
    data.setdefault("assigned_to", "cc_gulley")
    try:
        res = get_supabase().table("ceo_tasks").insert(data).execute()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Database error creating task: {exc}") from exc
    return {"ok": True, "task": _to_client((res.data or [{}])[0])}


@router.patch("/{task_id}")
def update_task(task_id: str, body: dict) -> dict:
    data = _from_client(body)
    if not data:
        raise HTTPException(400, "no updatable fields supplied")
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        res = get_supabase().table("ceo_tasks").update(data).eq("id", task_id).execute()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Database error updating task: {exc}") from exc
    if not (res.data or []):
        raise HTTPException(404, "task not found")
    return {"ok": True, "task": _to_client(res.data[0])}


@router.delete("/{task_id}")
def delete_task(task_id: str) -> dict:
    try:
        get_supabase().table("ceo_tasks").delete().eq("id", task_id).execute()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Database error deleting task: {exc}") from exc
    return {"ok": True}


@router.post("/send-to-agent")
def send_tasks_to_agent(body: dict) -> dict:
    """Push the current open task list into the assigned agent's NEXUS memory.

    Body: {owner?, agent?}. Reads the open tasks for `owner` and writes them as
    a standing directive so CC Gulley sees the live list on its next run.
    """
    from ..agents import memory as mem

    owner = (body.get("owner") or "mark").strip()
    agent = (body.get("agent") or "cc_gulley").strip()
    sb = get_supabase()
    try:
        rows = (
            sb.table("ceo_tasks")
            .select("*")
            .eq("owner", owner)
            .eq("done", False)
            .order("due_date")
            .execute()
            .data
            or []
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Database error reading tasks: {exc}") from exc

    tasks = [_to_client(r) for r in rows]
    if not tasks:
        return {"ok": True, "count": 0, "note": "no open tasks to send"}

    ts = datetime.now(timezone.utc).isoformat()
    lines = []
    for i, t in enumerate(tasks, 1):
        line = f"{i}. [{(t['pri'] or 'med').upper()}] {t['title']}"
        if t["due"]:
            line += f" (Due: {t['due']})"
        if t["desc"]:
            line += f"\n   Notes: {t['desc']}"
        lines.append(line)
    message = "CEO TASK LIST — MARK ODOM → CC GULLEY\n\n" + "\n\n".join(lines)

    directive = {
        "subject": "CEO Task List — Mark Odom",
        "message": message,
        "tasks": tasks,
        "issued_at": ts,
        "from": "commander",
    }
    mem.remember(agent, "commander_task_list", directive, confidence=0.95,
                 source_agent="commander", summary=f"{len(tasks)} open CEO tasks")
    return {"ok": True, "count": len(tasks), "agent": agent, "issued_at": ts}

"""IEBC Executive Command — 18 executives, KPI engine, triage system,
daily briefs, contingency plans, Commander dashboard.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..supabase_client import get_supabase
from ..logging_service import get_logger
from .deps import require_bearer

log = get_logger("3ll.executives")

router = APIRouter(dependencies=[Depends(require_bearer)])


# ── Pydantic models ───────────────────────────────────────────────────────────

class EscalationCreate(BaseModel):
    tier: int
    event_type: str
    description: str | None = None
    load_id: str | None = None
    driver_id: str | None = None
    assigned_to: str | None = None


class EscalationPatch(BaseModel):
    status: str | None = None
    resolution_notes: str | None = None
    auto_resolved: bool | None = None
    tier: int | None = None  # to escalate to next tier
    escalated_from_tier: int | None = None


class KpiSnapshotCreate(BaseModel):
    executive_id: str
    kpi_name: str
    target_value: float | None = None
    current_value: float | None = None
    unit: str | None = None
    status: str = "on_track"
    notes: str | None = None
    snapshot_date: str | None = None


class BriefCreate(BaseModel):
    tier1_resolved: int = 0
    tier2_resolved: int = 0
    tier3_items: list[Any] = []
    fleet_uptime_pct: float = 99.99
    active_loads: int = 0
    revenue_today: float = 0.0
    alerts: list[Any] = []
    master_scores: dict[str, Any] = {}
    summary: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _group_by_dept(executives: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for ex in executives:
        dept = ex.get("department", "unknown")
        out.setdefault(dept, []).append(ex)
    return out


def _default_master_scores() -> dict:
    return {
        "growth_velocity": {
            "score": 87,
            "owners": ["Sterling Pierce", "Benjamin Mercer"],
            "trend": "up",
        },
        "operational_margin": {
            "score": 94,
            "owners": ["Eleanor Wei", "Dr. Anika Patel"],
            "trend": "stable",
        },
        "system_integrity": {
            "score": 99,
            "owners": ["Marcus Reid", "Jamie Park"],
            "trend": "up",
        },
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/executives")
def list_executives() -> dict:
    """List all 18 executives grouped by department."""
    sb = get_supabase()
    res = sb.table("executives").select("*").order("department").execute()
    executives = res.data or []
    return {
        "total": len(executives),
        "grouped": _group_by_dept(executives),
        "all": executives,
    }


@router.get("/executives/dashboard")
def commander_dashboard() -> dict:
    """Commander's 3 master scores + org summary + brief availability."""
    sb = get_supabase()

    # Org counts
    execs = sb.table("executives").select("id,department", count="exact").execute()
    cabinet = sb.table("executives").select("id", count="exact").eq("reports_to", "commander").execute()

    # Active escalations
    esc = (
        sb.table("triage_escalations")
        .select("id,tier", count="exact")
        .in_("status", ["open", "in_review"])
        .execute()
    )

    # Today's brief
    today_str = date.today().isoformat()
    brief_res = sb.table("daily_briefs").select("id,master_scores").eq("date", today_str).limit(1).execute()
    brief_available = bool(brief_res.data)

    # Tier-3 open items today
    tier3 = (
        sb.table("triage_escalations")
        .select("id,event_type,assigned_to,status")
        .eq("tier", 3)
        .in_("status", ["open", "in_review"])
        .execute()
    )

    master_scores = _default_master_scores()
    if brief_res.data and brief_res.data[0].get("master_scores"):
        stored = brief_res.data[0]["master_scores"]
        if isinstance(stored, dict) and stored:
            master_scores = stored

    return {
        "master_scores": master_scores,
        "org": {
            "cabinet_count": cabinet.count or 0,
            "total_workforce": execs.count or 0,
            "active_escalations": esc.count or 0,
        },
        "daily_brief_available": brief_available,
        "tier3_items_today": tier3.data or [],
    }


@router.get("/executives/brief/today")
def get_today_brief() -> dict:
    """Return today's State of the Fleet brief authored by Dr. Evelyn Sterling."""
    sb = get_supabase()
    today_str = date.today().isoformat()
    res = (
        sb.table("daily_briefs")
        .select("*")
        .eq("date", today_str)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No brief for today yet")
    return {"brief": res.data[0]}


@router.post("/executives/brief")
def generate_daily_brief(payload: BriefCreate) -> dict:
    """Generate and store today's State of the Fleet brief (called by scheduler)."""
    sb = get_supabase()
    today_str = date.today().isoformat()

    # Use stored master_scores if provided, otherwise defaults
    master_scores = payload.master_scores or _default_master_scores()

    row = {
        "date": today_str,
        "authored_by": "Dr. Evelyn Sterling",
        "tier1_resolved": payload.tier1_resolved,
        "tier2_resolved": payload.tier2_resolved,
        "tier3_items": payload.tier3_items,
        "fleet_uptime_pct": payload.fleet_uptime_pct,
        "active_loads": payload.active_loads,
        "revenue_today": payload.revenue_today,
        "alerts": payload.alerts,
        "master_scores": master_scores,
        "summary": payload.summary,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    res = sb.table("daily_briefs").insert(row).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to store brief")
    log.info("Daily brief stored for %s", today_str)
    return {"ok": True, "brief": res.data[0]}


@router.get("/executives/escalations")
def list_escalations(
    tier: int | None = None,
    status_filter: str | None = None,
) -> dict:
    """All open escalations grouped by tier."""
    sb = get_supabase()
    q = sb.table("triage_escalations").select("*").order("created_at", desc=True)
    if tier is not None:
        q = q.eq("tier", tier)
    if status_filter:
        q = q.eq("status", status_filter)
    res = q.execute()
    items = res.data or []

    grouped: dict[str, list] = {"1": [], "2": [], "3": []}
    for item in items:
        key = str(item.get("tier", "1"))
        grouped.setdefault(key, []).append(item)

    return {"total": len(items), "grouped_by_tier": grouped, "items": items}


@router.post("/executives/escalations")
def create_escalation(payload: EscalationCreate) -> dict:
    """Create a new triage escalation (called by AI agents or other routes)."""
    if payload.tier not in (1, 2, 3):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "tier must be 1, 2, or 3")
    sb = get_supabase()
    row: dict[str, Any] = {
        "tier": payload.tier,
        "event_type": payload.event_type,
        "description": payload.description,
        "assigned_to": payload.assigned_to,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload.load_id:
        row["load_id"] = payload.load_id
    if payload.driver_id:
        row["driver_id"] = payload.driver_id

    res = sb.table("triage_escalations").insert(row).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create escalation")
    log.info("Escalation created tier=%s type=%s", payload.tier, payload.event_type)
    return {"ok": True, "escalation": res.data[0]}


@router.patch("/executives/escalations/{escalation_id}")
def patch_escalation(escalation_id: str, payload: EscalationPatch) -> dict:
    """Resolve, escalate, or update an escalation."""
    sb = get_supabase()

    # Verify it exists
    existing = sb.table("triage_escalations").select("id,tier,status").eq("id", escalation_id).single().execute()
    if not existing.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Escalation not found")

    updates: dict[str, Any] = {}
    if payload.status is not None:
        updates["status"] = payload.status
        if payload.status == "resolved":
            updates["resolved_at"] = datetime.now(timezone.utc).isoformat()
    if payload.resolution_notes is not None:
        updates["resolution_notes"] = payload.resolution_notes
    if payload.auto_resolved is not None:
        updates["auto_resolved"] = payload.auto_resolved
    if payload.tier is not None:
        updates["tier"] = payload.tier
        updates["escalated_from_tier"] = payload.escalated_from_tier or existing.data.get("tier")

    if not updates:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "No fields to update")

    res = sb.table("triage_escalations").update(updates).eq("id", escalation_id).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to update escalation")
    log.info("Escalation %s updated: %s", escalation_id, updates)
    return {"ok": True, "escalation": res.data[0]}


@router.get("/executives/kpis")
def list_kpis(executive_id: str | None = None) -> dict:
    """All KPI snapshots, latest per executive."""
    sb = get_supabase()
    q = (
        sb.table("executive_kpi_snapshots")
        .select("*,executives(name,title,department)")
        .order("snapshot_date", desc=True)
    )
    if executive_id:
        q = q.eq("executive_id", executive_id)
    res = q.execute()
    snapshots = res.data or []

    # Deduplicate to latest per executive
    seen: dict[str, dict] = {}
    for snap in snapshots:
        eid = snap.get("executive_id", "")
        if eid not in seen:
            seen[eid] = snap

    return {
        "total": len(snapshots),
        "latest_per_executive": list(seen.values()),
        "all": snapshots,
    }


@router.post("/executives/kpis")
def record_kpi_snapshot(payload: KpiSnapshotCreate) -> dict:
    """Record a KPI snapshot for an executive."""
    sb = get_supabase()

    # Verify executive exists
    exec_res = sb.table("executives").select("id,name").eq("id", payload.executive_id).single().execute()
    if not exec_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Executive {payload.executive_id} not found")

    snap_date = payload.snapshot_date or date.today().isoformat()
    row: dict[str, Any] = {
        "executive_id": payload.executive_id,
        "kpi_name": payload.kpi_name,
        "target_value": payload.target_value,
        "current_value": payload.current_value,
        "unit": payload.unit,
        "status": payload.status,
        "notes": payload.notes,
        "snapshot_date": snap_date,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = sb.table("executive_kpi_snapshots").insert(row).execute()
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to record KPI snapshot")
    log.info("KPI snapshot recorded: %s for exec %s", payload.kpi_name, exec_res.data["name"])
    return {"ok": True, "snapshot": res.data[0]}


@router.get("/executives/contingencies")
def list_contingencies() -> dict:
    """List all 5 contingency plans with trigger history."""
    sb = get_supabase()
    res = sb.table("contingency_plans").select("*").order("trigger_count", desc=True).execute()
    plans = res.data or []
    return {"total": len(plans), "plans": plans}


@router.post("/executives/contingencies/{contingency_id}/trigger")
def trigger_contingency(contingency_id: str) -> dict:
    """Log a contingency plan being triggered."""
    sb = get_supabase()

    existing = sb.table("contingency_plans").select("id,name,trigger_count").eq("id", contingency_id).single().execute()
    if not existing.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contingency plan not found")

    new_count = (existing.data.get("trigger_count") or 0) + 1
    now = datetime.now(timezone.utc).isoformat()

    res = (
        sb.table("contingency_plans")
        .update({"trigger_count": new_count, "last_triggered_at": now})
        .eq("id", contingency_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to trigger contingency")

    plan_name = existing.data["name"]
    log.info("Contingency triggered: %s (count=%d)", plan_name, new_count)
    return {"ok": True, "plan": res.data[0], "trigger_count": new_count}


@router.get("/executives/{exec_id}")
def get_executive(exec_id: str) -> dict:
    """Executive profile + latest KPIs + recent escalations."""
    sb = get_supabase()

    exec_res = sb.table("executives").select("*").eq("id", exec_id).single().execute()
    if not exec_res.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Executive not found")

    kpis_res = (
        sb.table("executive_kpi_snapshots")
        .select("*")
        .eq("executive_id", exec_id)
        .order("snapshot_date", desc=True)
        .limit(10)
        .execute()
    )

    # Escalations assigned to this exec
    name = exec_res.data.get("name", "")
    esc_res = (
        sb.table("triage_escalations")
        .select("*")
        .eq("assigned_to", name)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )

    return {
        "executive": exec_res.data,
        "kpi_history": kpis_res.data or [],
        "recent_escalations": esc_res.data or [],
    }

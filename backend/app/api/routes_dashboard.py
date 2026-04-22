"""Dashboard aggregates — power the Ops Suite (Stage 5 steps 91-97)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


def _mtd_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


@router.get("/kpis")
def kpis() -> dict:
    sb = get_supabase()
    mtd = _mtd_iso()

    carriers = sb.table("active_carriers").select("id,status", count="exact").execute()
    active = sb.table("active_carriers").select("id", count="exact").eq("status", "active").execute()
    loads = sb.table("loads").select("id,rate_total,rate_per_mile", count="exact").gte("created_at", mtd).execute()
    unpaid = sb.table("invoices").select("amount", count="exact").eq("status", "Unpaid").execute()

    gross_mtd = sum((r.get("rate_total") or 0) for r in (loads.data or []))
    rpms = [r.get("rate_per_mile") for r in (loads.data or []) if r.get("rate_per_mile")]
    avg_rpm = round(sum(rpms) / len(rpms), 2) if rpms else 0
    unpaid_total = sum((r.get("amount") or 0) for r in (unpaid.data or []))

    return {
        "total_carriers": carriers.count or 0,
        "active_carriers": active.count or 0,
        "mtd_loads": loads.count or 0,
        "mtd_gross": float(gross_mtd),
        "avg_rpm": float(avg_rpm),
        "mtd_dispatch_fees": float(gross_mtd) * 0.10,
        "unpaid_invoices": unpaid.count or 0,
        "unpaid_total": float(unpaid_total),
    }


@router.get("/recent-loads")
def recent_loads(limit: int = 10) -> dict:
    res = (
        get_supabase().table("loads")
        .select("id,broker_name,load_number,origin_city,origin_state,"
                "dest_city,dest_state,rate_total,status,created_at")
        .order("created_at", desc=True).limit(limit).execute()
    )
    return {"items": res.data or []}


# ------------- Stage 5 Ops Suite panels -------------

@router.get("/agents/status")
def agents_status() -> dict:
    """Step 91 — per-agent last run + next scheduled."""
    from ..agents.router import available_agents
    sb = get_supabase()
    out = []
    for agent in available_agents():
        last = (
            sb.table("agent_runs").select("*")
            .eq("agent", agent).order("started_at", desc=True).limit(1).execute().data or []
        )
        pending = (
            sb.table("agent_tasks").select("id,run_at", count="exact")
            .eq("agent", agent).eq("status", "pending").execute()
        )
        out.append({
            "agent": agent,
            "last_run": (last[0] if last else None),
            "pending_count": pending.count or 0,
        })
    return {"items": out}


@router.get("/compliance/board")
def compliance_board() -> dict:
    """Step 95 — Shield compliance snapshot (red/yellow/green)."""
    sb = get_supabase()
    rows = (
        sb.table("insurance_compliance")
        .select("carrier_id, safety_light, policy_expiry, last_checked_at, operating_status, safety_rating")
        .execute().data or []
    )
    red = [r for r in rows if r.get("safety_light") == "red"]
    yellow = [r for r in rows if r.get("safety_light") == "yellow"]
    return {
        "totals": {"red": len(red), "yellow": len(yellow), "green": len(rows) - len(red) - len(yellow)},
        "red": red, "yellow": yellow,
    }


@router.get("/finance/overview")
def finance_overview() -> dict:
    """Step 96 — Penny + Settler rollups."""
    sb = get_supabase()
    mtd = _mtd_iso()
    settlements = (
        sb.table("driver_settlements").select("gross_amount, deductions, status")
        .gte("period_end", mtd[:10]).execute().data or []
    )
    stripe_events = (
        sb.table("stripe_events").select("type, created_at")
        .gte("created_at", mtd).limit(500).execute().data or []
    )
    type_counts: dict[str, int] = {}
    for e in stripe_events:
        type_counts[e["type"]] = type_counts.get(e["type"], 0) + 1
    gross = sum(float(s.get("gross_amount") or 0) for s in settlements)
    net   = sum(float(s.get("gross_amount") or 0) - float(s.get("deductions") or 0) for s in settlements)
    return {
        "mtd_settlements_gross": gross,
        "mtd_settlements_net": net,
        "stripe_event_counts": type_counts,
        "settlements_count": len(settlements),
    }


@router.get("/kpi-history")
def kpi_history(hours: int = 24) -> dict:
    """Step 97 — KPI time-series for the observability strip."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = (
        get_supabase().table("kpi_snapshots").select("*")
        .gte("ts", cutoff).order("ts").execute().data or []
    )
    return {"items": rows}


@router.get("/pipeline/kanban")
def pipeline_kanban() -> dict:
    """Step 93 — lead pipeline grouped by stage."""
    sb = get_supabase()
    stages = ["new", "hot", "warm", "cold", "contacted", "won", "lost"]
    out = {}
    for stage in stages:
        rows = (
            sb.table("leads").select("*").eq("stage", stage)
            .order("score", desc=True).limit(50).execute().data or []
        )
        out[stage] = rows
    return {"columns": out}


@router.get("/fleet/live")
def fleet_live() -> dict:
    """Step 94 — last known telemetry per truck (for map)."""
    sb = get_supabase()
    rows = (
        sb.table("truck_telemetry").select("truck_id, carrier_id, lat, lng, speed_mph, ts")
        .order("ts", desc=True).limit(2000).execute().data or []
    )
    seen: dict[str, dict] = {}
    for r in rows:
        key = r.get("truck_id")
        if key and key not in seen:
            seen[key] = r
    return {"trucks": list(seen.values())}

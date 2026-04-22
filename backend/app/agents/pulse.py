"""Pulse — KPI snapshots + daily digest (step 70)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..integrations.email import send_email
from ..integrations.slack import post_ops
from ..logging_service import log_agent


def score_driver(driver_id: str) -> dict[str, Any]:
    try:
        from ..supabase_client import get_supabase
        recent = (
            get_supabase().table("driver_hos_status")
            .select("duty_status, violation_flags, ts")
            .eq("driver_id", driver_id).order("ts", desc=True).limit(200).execute()
        ).data or []
    except Exception:  # noqa: BLE001
        recent = []
    violations = sum(1 for r in recent if r.get("violation_flags"))
    wellness = max(0, 100 - violations * 5)
    return {"driver_id": driver_id, "wellness_score": wellness, "recent_violations": violations}


def kpi_snapshot() -> dict[str, Any]:
    """Aggregate live dashboard counters and persist to kpi_snapshots."""
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        carriers = sb.table("active_carriers").select("id, status").execute().data or []
        today = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        loads = sb.table("loads").select("id, status, rate_total").gte(
            "created_at", today).execute().data or []
        leads = sb.table("leads").select("id, stage").execute().data or []
        snap = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "carriers_active": sum(1 for c in carriers if c.get("status") == "active"),
            "carriers_onboarding": sum(1 for c in carriers if c.get("status") == "onboarding"),
            "carriers_suspended": sum(1 for c in carriers if c.get("status") == "suspended"),
            "loads_today": len(loads),
            "gross_today": sum(float(l.get("rate_total") or 0) for l in loads),
            "leads_hot": sum(1 for l in leads if l.get("stage") == "hot"),
            "leads_warm": sum(1 for l in leads if l.get("stage") == "warm"),
        }
        sb.table("kpi_snapshots").insert(snap).execute()
        return {"status": "ok", **snap}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}


def daily_digest() -> dict[str, Any]:
    snap = kpi_snapshot()
    if snap.get("status") != "ok":
        return snap
    msg = (
        f"*3 Lakes daily digest* — {snap['ts'][:10]}\n"
        f"Active carriers: *{snap['carriers_active']}*   "
        f"Onboarding: {snap['carriers_onboarding']}   "
        f"Suspended: {snap['carriers_suspended']}\n"
        f"Loads today: *{snap['loads_today']}*   "
        f"Gross today: *${snap['gross_today']:,.0f}*\n"
        f"Pipeline — hot: *{snap['leads_hot']}*  warm: {snap['leads_warm']}"
    )
    post_ops(msg)
    log_agent("pulse", "daily_digest", result="sent")
    return {"status": "ok", "sent": True}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind") or "driver"
    if kind == "kpi_snapshot":
        return {"agent": "pulse", **kpi_snapshot()}
    if kind == "daily_digest":
        return {"agent": "pulse", **daily_digest()}
    driver_id = payload.get("driver_id", "")
    return {"agent": "pulse", "status": "ok",
            **(score_driver(driver_id) if driver_id else {"note": "pass driver_id"})}

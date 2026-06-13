"""LF BizDev API routes — email/call campaign triggers + activity feed.

POST /api/lf-bizdev/run-campaign/   fire full email+call sequence
POST /api/lf-bizdev/run-calls/      fire call sequence only
POST /api/lf-bizdev/run-emails/     fire email sequence only
GET  /api/lf-bizdev/activity/       recent outreach log (last 50)
GET  /api/lf-bizdev/stats/          per-prospect sequence stats
"""
from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Depends

from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(prefix="/api/lf-bizdev", dependencies=[Depends(require_bearer)])


def _bg(fn, *args, **kwargs) -> None:
    """Fire and forget in a daemon thread."""
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()


@router.post("/run-campaign/")
def run_campaign(body: dict = {}) -> dict[str, Any]:  # noqa: B006
    """Trigger full email + call drip sequence for all eligible BizDev prospects."""
    from ..agents.lf_bizdev import run as lf_run  # noqa: PLC0415

    result = lf_run(payload=body)
    return {"ok": True, "result": result}


@router.post("/run-calls/")
def run_calls(body: dict = {}) -> dict[str, Any]:  # noqa: B006
    """Fire Bland AI call sequence for warm BizDev prospects."""
    from ..agents.lf_bizdev import run_call_sequence  # noqa: PLC0415

    call_limit = (body or {}).get("call_limit", 20)
    result = run_call_sequence(daily_limit=call_limit)
    return {"ok": True, "result": result}


@router.post("/run-emails/")
def run_emails(body: dict = {}) -> dict[str, Any]:  # noqa: B006
    """Fire email drip sequence for eligible BizDev prospects."""
    from ..agents.lf_bizdev import run_email_sequence  # noqa: PLC0415

    email_limit = (body or {}).get("email_limit", 30)
    result = run_email_sequence(daily_limit=email_limit)
    return {"ok": True, "result": result}


@router.get("/activity/")
def get_activity(limit: int = 50) -> dict[str, Any]:
    """Return recent outreach log entries with prospect details."""
    db = get_supabase()

    logs = (
        db.table("lf_bd_outreach_log")
        .select("id,prospect_id,channel,step,subject,status,call_id,created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    ).data or []

    # Enrich with prospect company name
    prospect_ids = list({str(r["prospect_id"]) for r in logs if r.get("prospect_id")})
    prospect_map: dict[str, str] = {}
    if prospect_ids:
        try:
            rows = (
                db.table("lf_bd_prospects")
                .select("id,company,sector,rep")
                .in_("id", prospect_ids)
                .execute()
            ).data or []
            for row in rows:
                prospect_map[str(row["id"])] = row
        except Exception:  # noqa: BLE001
            pass

    enriched = []
    for log in logs:
        pid = str(log.get("prospect_id") or "")
        prospect_info = prospect_map.get(pid, {})
        enriched.append({
            **log,
            "company": prospect_info.get("company", "Unknown"),
            "sector": prospect_info.get("sector", ""),
            "rep": prospect_info.get("rep", ""),
        })

    return {"logs": enriched, "count": len(enriched)}


@router.get("/stats/")
def get_stats() -> dict[str, Any]:
    """Return sequence stats per prospect and per-sector summaries."""
    db = get_supabase()

    prospects = (
        db.table("lf_bd_prospects")
        .select("id,company,sector,rep,status,sequence_step,email_count,call_count,last_email_at,last_call_at")
        .order("company")
        .execute()
    ).data or []

    # Per-sector aggregates
    sector_stats: dict[str, dict] = {
        "healthcare": {"prospects": 0, "emails": 0, "calls": 0},
        "enterprise": {"prospects": 0, "emails": 0, "calls": 0},
        "platform": {"prospects": 0, "emails": 0, "calls": 0},
    }
    for p in prospects:
        sec = p.get("sector") or "enterprise"
        if sec not in sector_stats:
            sector_stats[sec] = {"prospects": 0, "emails": 0, "calls": 0}
        sector_stats[sec]["prospects"] += 1
        sector_stats[sec]["emails"] += p.get("email_count") or 0
        sector_stats[sec]["calls"] += p.get("call_count") or 0

    return {
        "prospects": prospects,
        "sector_stats": sector_stats,
        "total": len(prospects),
    }

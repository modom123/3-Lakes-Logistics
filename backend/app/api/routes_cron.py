"""Scheduled / cron trigger endpoints.

All routes are protected by a cron secret header so only the scheduler
(GitHub Actions, Render cron, etc.) can fire them.

Routes:
  POST /api/cron/cdl-sweep          — scan CDL expirations, fire alerts
  POST /api/cron/fmcsa-ingest       — scrape FMCSA new-entrant leads
  POST /api/cron/beacon-digest      — send ops daily digest email
  POST /api/cron/settlement-batch   — run weekly ACH settlements for all carriers
  POST /api/cron/mark-overdue       — auto-flag past-due invoices as Overdue
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Header, HTTPException, status

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase

router = APIRouter(tags=["cron"])


def _check_cron_secret(x_cron_secret: str | None = Header(default=None)) -> None:
    s = get_settings()
    expected = s.cron_secret
    if expected and x_cron_secret != expected:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid cron secret")


# ── CDL Sweep ─────────────────────────────────────────────────────────────────

@router.post("/cdl-sweep", dependencies=[])
def cron_cdl_sweep(x_cron_secret: str | None = Header(default=None)) -> dict:
    """Flag CDLs expiring within 30 days and send compliance alerts."""
    _check_cron_secret(x_cron_secret)

    sb = get_supabase()
    today = date.today()
    warn_before = (today + timedelta(days=30)).isoformat()

    res = (
        sb.table("driver_cdl")
        .select("id,driver_id,cdl_number,expiration_date,carrier_id")
        .lte("expiration_date", warn_before)
        .gte("expiration_date", today.isoformat())
        .execute()
    )
    expiring = res.data or []

    alerted = 0
    for cdl in expiring:
        days_left = (date.fromisoformat(cdl["expiration_date"]) - today).days
        try:
            from ..agents import signal as signal_agent
            signal_agent.run({
                "action": "cdl_alert",
                "driver_id": cdl.get("driver_id"),
                "cdl_number": cdl.get("cdl_number"),
                "expiration_date": cdl.get("expiration_date"),
                "days_until_expiry": days_left,
            })
            alerted += 1
        except Exception:
            pass

    log_agent("shield", "cdl_sweep", payload={"expiring_count": len(expiring), "alerted": alerted})
    return {"ok": True, "expiring_cdls": len(expiring), "alerts_sent": alerted}


# ── FMCSA Ingest ──────────────────────────────────────────────────────────────

@router.post("/fmcsa-ingest")
def cron_fmcsa_ingest(x_cron_secret: str | None = Header(default=None)) -> dict:
    """Scrape FMCSA new-entrant list and insert qualified leads."""
    _check_cron_secret(x_cron_secret)

    try:
        from ..prospecting.fmcsa_scraper import ingest
        result = ingest()
    except Exception as exc:
        log_agent("scout", "fmcsa_ingest_error", payload={"error": str(exc)})
        raise HTTPException(500, f"FMCSA ingest failed: {exc}") from exc

    log_agent("scout", "fmcsa_ingest", payload=result)
    return {"ok": True, **result}


# ── Beacon Digest ─────────────────────────────────────────────────────────────

@router.post("/beacon-digest")
def cron_beacon_digest(x_cron_secret: str | None = Header(default=None)) -> dict:
    """Generate and email the daily ops digest."""
    _check_cron_secret(x_cron_secret)

    try:
        from ..agents import beacon as beacon_agent
        result = beacon_agent.run({})
    except Exception as exc:
        log_agent("beacon", "digest_error", payload={"error": str(exc)})
        raise HTTPException(500, f"beacon digest failed: {exc}") from exc

    log_agent("beacon", "digest_sent", payload=result)
    return {"ok": True, "result": result}


# ── Settlement Batch ──────────────────────────────────────────────────────────

@router.post("/settlement-batch")
def cron_settlement_batch(x_cron_secret: str | None = Header(default=None)) -> dict:
    """Run weekly ACH settlement for every active carrier."""
    _check_cron_secret(x_cron_secret)

    sb = get_supabase()
    today = date.today()
    week_start = (today - timedelta(days=today.weekday() + 7)).isoformat()
    week_end = (today - timedelta(days=today.weekday())).isoformat()

    carriers_res = (
        sb.table("active_carriers")
        .select("id,carrier_name")
        .eq("status", "active")
        .execute()
    )
    carriers = carriers_res.data or []

    results = []
    for carrier in carriers:
        try:
            from ..agents import settler as settler_agent
            drivers_res = (
                sb.table("active_drivers")
                .select("id")
                .eq("carrier_id", carrier["id"])
                .execute()
            )
            for driver in (drivers_res.data or []):
                r = settler_agent.run({
                    "carrier_id": carrier["id"],
                    "driver_id": driver["id"],
                    "week_start": week_start,
                    "week_end": week_end,
                })
                results.append({"driver_id": driver["id"], "result": r})
        except Exception as exc:
            results.append({"carrier_id": carrier["id"], "error": str(exc)})

    log_agent("settler", "batch_settlement", payload={"carriers": len(carriers), "records": len(results)})
    return {
        "ok": True,
        "week": f"{week_start} → {week_end}",
        "carriers_processed": len(carriers),
        "settlement_records": len(results),
        "details": results,
    }


# ── Mark Overdue Invoices ─────────────────────────────────────────────────────

@router.post("/mark-overdue")
def cron_mark_overdue(x_cron_secret: str | None = Header(default=None)) -> dict:
    """Auto-flag all past-due unpaid invoices as Overdue."""
    _check_cron_secret(x_cron_secret)

    sb = get_supabase()
    today = date.today().isoformat()

    res = (
        sb.table("invoices")
        .update({"status": "Overdue"})
        .eq("status", "Unpaid")
        .lt("due_date", today)
        .execute()
    )
    count = len(res.data or [])
    log_agent("settler", "mark_overdue_batch", payload={"flagged": count, "as_of": today})
    return {"ok": True, "invoices_flagged_overdue": count, "as_of": today}

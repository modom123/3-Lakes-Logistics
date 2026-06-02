"""Event-driven trigger endpoints — called by the EAGLE EYE after Supabase writes.

The frontend saves loads/status changes directly to Supabase via the JS client.
After each write, it hits one of these endpoints so the execution engine fires
the right domain in the background.

Endpoints
─────────
  POST /api/triggers/onboarding   → fires onboarding domain (called by intake form)
  POST /api/triggers/load_booked  → fires dispatch domain   (load status → Booked)
  POST /api/triggers/pickup       → fires transit domain    (load status → En Route)
  POST /api/triggers/delivered    → fires settlement domain (load status → Delivered)
  POST /api/triggers/compliance   → fires compliance sweep  (manual or cron)
  GET  /api/triggers/status       → last 20 trigger events from agent_log
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel

from ..triggers import (
    fire_analytics_update,
    fire_compliance_sweep,
    fire_dispatch,
    fire_natco_covered,
    fire_natco_delivered,
    fire_natco_morning_brief,
    fire_natco_trade_posted,
    fire_onboarding,
    fire_settlement,
    fire_transit,
)
from ..logging_service import log_agent
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


# ── request bodies ────────────────────────────────────────────────────────────

class OnboardingTrigger(BaseModel):
    carrier_id: str

class LoadTrigger(BaseModel):
    carrier_id: str | None = None
    load_id: str
    load_number: str | None = None
    driver_name: str | None = None
    origin: str | None = None
    destination: str | None = None
    rate: float | None = None

class ComplianceTrigger(BaseModel):
    carrier_id: str | None = None   # None = sweep all carriers

class NatcoTradeTrigger(BaseModel):
    load_id: str
    load_number: str | None = None
    broker_pay: float = 0
    carrier_pay: float | None = None
    origin: str = ""
    equipment: str = "Dry Van 53'"
    carrier_name: str | None = None


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/onboarding")
def trigger_onboarding(req: OnboardingTrigger, bg: BackgroundTasks) -> dict:
    """Fire after a carrier intake form is submitted."""
    bg.add_task(fire_onboarding, req.carrier_id)
    log_agent("atlas", "trigger.onboarding", carrier_id=req.carrier_id,
              result="queued")
    return {"ok": True, "domain": "onboarding", "carrier_id": req.carrier_id}


@router.post("/load_booked")
def trigger_load_booked(req: LoadTrigger, bg: BackgroundTasks) -> dict:
    """Fire when a load is created or status changes to Booked."""
    bg.add_task(fire_dispatch, req.carrier_id, req.load_id,
                {"load_number": req.load_number, "origin": req.origin,
                 "destination": req.destination, "rate_total": req.rate})
    log_agent("atlas", "trigger.dispatch", carrier_id=req.carrier_id,
              payload={"load_id": req.load_id}, result="queued")
    return {"ok": True, "domain": "dispatch", "load_id": req.load_id}


@router.post("/pickup")
def trigger_pickup(req: LoadTrigger, bg: BackgroundTasks) -> dict:
    """Fire when a driver confirms pickup (load status → En Route)."""
    bg.add_task(fire_transit, req.carrier_id, req.load_id,
                {"load_id": req.load_id})
    log_agent("atlas", "trigger.transit", carrier_id=req.carrier_id,
              payload={"load_id": req.load_id}, result="queued")
    return {"ok": True, "domain": "transit", "load_id": req.load_id}


@router.post("/delivered")
def trigger_delivered(req: LoadTrigger, bg: BackgroundTasks) -> dict:
    """Fire when a delivery is confirmed (load status → Delivered / Completed)."""
    bg.add_task(fire_settlement, req.carrier_id, req.load_id,
                {"load_id": req.load_id, "rate_total": req.rate})
    log_agent("atlas", "trigger.settlement", carrier_id=req.carrier_id,
              payload={"load_id": req.load_id}, result="queued")
    return {"ok": True, "domain": "settlement", "load_id": req.load_id}


@router.post("/compliance")
def trigger_compliance(req: ComplianceTrigger, bg: BackgroundTasks) -> dict:
    """Fire compliance sweep — daily cron or manual trigger from the EAGLE EYE."""
    bg.add_task(fire_compliance_sweep)
    log_agent("atlas", "trigger.compliance", carrier_id=req.carrier_id,
              result="queued")
    return {"ok": True, "domain": "compliance"}


@router.post("/natco/trade_posted")
def trigger_natco_trade_posted(req: NatcoTradeTrigger, bg: BackgroundTasks) -> dict:
    """Fire when a new NATCO trade is posted — Grace analyzes rate, Dominic finds carriers."""
    bg.add_task(fire_natco_trade_posted, req.load_id, req.broker_pay,
                req.carrier_pay, req.origin, req.equipment)
    log_agent("rex_sterling", "trigger.natco.trade_posted",
              payload={"load_id": req.load_id, "broker_pay": req.broker_pay}, result="queued")
    return {"ok": True, "domain": "natco.trade_posted", "load_id": req.load_id}


@router.post("/natco/covered")
def trigger_natco_covered(req: NatcoTradeTrigger, bg: BackgroundTasks) -> dict:
    """Fire when a carrier is assigned to a NATCO load."""
    bg.add_task(fire_natco_covered, req.load_id,
                req.carrier_name or "", req.load_number or req.load_id)
    log_agent("dominic_voss", "trigger.natco.covered",
              payload={"load_id": req.load_id, "carrier": req.carrier_name}, result="queued")
    return {"ok": True, "domain": "natco.covered", "load_id": req.load_id}


@router.post("/natco/delivered")
def trigger_natco_delivered(req: NatcoTradeTrigger, bg: BackgroundTasks) -> dict:
    """Fire when a NATCO load is delivered — Sofia logs P&L, creates invoice."""
    bg.add_task(fire_natco_delivered, req.load_id, req.broker_pay,
                req.carrier_pay or 0, req.load_number or req.load_id)
    log_agent("rex_sterling", "trigger.natco.delivered",
              payload={"load_id": req.load_id, "spread": req.broker_pay - (req.carrier_pay or 0)},
              result="queued")
    return {"ok": True, "domain": "natco.delivered", "load_id": req.load_id}


@router.post("/natco/morning_brief")
def trigger_natco_morning_brief(bg: BackgroundTasks) -> dict:
    """Manually fire the NATCO morning brief (also runs daily at 07:00 UTC)."""
    bg.add_task(fire_natco_morning_brief)
    log_agent("rex_sterling", "trigger.natco.morning_brief", result="queued")
    return {"ok": True, "domain": "natco.morning_brief"}


@router.post("/analytics")
def trigger_analytics(bg: BackgroundTasks) -> dict:
    """Manually refresh analytics domain."""
    bg.add_task(fire_analytics_update)
    log_agent("beacon", "trigger.analytics", result="queued")
    return {"ok": True, "domain": "analytics"}


@router.get("/status")
def trigger_status() -> dict:
    """Return recent trigger events from agent_log (agent=atlas)."""
    rows = (
        get_supabase()
        .table("agent_log")
        .select("*")
        .eq("agent", "atlas")
        .like("action", "trigger.%")
        .order("ts", desc=True)
        .limit(20)
        .execute()
    ).data or []
    return {"triggers": rows}

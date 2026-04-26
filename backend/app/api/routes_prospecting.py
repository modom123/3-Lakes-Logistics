"""Prospecting pipeline REST API.

Exposes the full outbound lead pipeline as callable endpoints so the
Ops Suite and cron jobs can trigger sequences.

Routes:
  GET  /api/prospecting/leads          — scored lead queue
  POST /api/prospecting/leads/{id}/sequence  — run a lead through the full pipeline
  POST /api/prospecting/leads/{id}/call      — trigger Vance outbound call
  POST /api/prospecting/leads/{id}/sms       — send outbound SMS via Signal
  POST /api/prospecting/leads/{id}/nurture   — enqueue in email nurture sequence
  POST /api/prospecting/owner-lookup         — resolve owner contact from DOT
  GET  /api/prospecting/funnel               — conversion funnel stats
  POST /api/prospecting/fmcsa-scrape         — trigger on-demand FMCSA ingest
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


# ── Lead Queue ────────────────────────────────────────────────────────────────

@router.get("/leads")
def list_prospecting_leads(
    min_score: int = 0,
    stage: str | None = None,
    limit: int = 100,
) -> dict:
    """Return scored leads eligible for outbound sequencing."""
    q = (
        get_supabase()
        .table("leads")
        .select("*")
        .gte("lead_score", min_score)
        .neq("stage", "dnc")
        .order("lead_score", desc=True)
        .limit(limit)
    )
    if stage:
        q = q.eq("stage", stage)
    items = q.execute().data or []
    return {"count": len(items), "items": items}


# ── Full Pipeline Sequence ────────────────────────────────────────────────────

@router.post("/leads/{lead_id}/sequence")
def run_sequence(lead_id: str) -> dict:
    """Run a lead through the full outbound pipeline: route → call/SMS/email."""
    sb = get_supabase()
    lead = sb.table("leads").select("*").eq("id", lead_id).maybe_single().execute().data
    if not lead:
        raise HTTPException(404, "lead not found")

    if lead.get("stage") == "dnc":
        return {"ok": False, "reason": "lead_is_dnc"}

    score = lead.get("lead_score") or 0
    phone = lead.get("phone") or lead.get("owner_phone")
    email = lead.get("email") or lead.get("owner_email")

    from ..prospecting.traffic_controller import pick_channel
    from ..prospecting.outbound_schedule import can_dial

    state = lead.get("home_state") or lead.get("state") or "IL"
    channel = pick_channel(lead)

    result: dict = {"lead_id": lead_id, "channel": channel, "score": score}

    if channel == "voice":
        if can_dial(state):
            from ..agents.vance import start_outbound_call
            vr = start_outbound_call(lead)
            result["call"] = vr
        else:
            result["call"] = {"status": "outside_hours", "state": state}

    elif channel == "sms":
        if can_dial(state):
            from ..prospecting.ab_testing import pick_variant
            variant = pick_variant(lead_id)
            from ..agents.signal import run as signal_run
            sr = signal_run({
                "action": "dispatch",
                "driver_phone": phone,
                "message": variant.get("body", f"Hi {lead.get('first_name', 'there')}, this is 3 Lakes Logistics — we dispatch owner-operators across 48 states. Interested? Reply YES."),
            })
            result["sms"] = sr
        else:
            result["sms"] = {"status": "outside_hours", "state": state}

    elif channel == "email":
        from ..agents.nova import run as nova_run
        nr = nova_run({
            "action": "welcome",
            "to_email": email,
            "carrier_name": lead.get("company_name") or lead.get("carrier_name"),
            "first_name": lead.get("first_name"),
        })
        result["email"] = nr

    # Advance stage
    sb.table("leads").update({
        "stage": "contacted",
        "call_count": (lead.get("call_count") or 0) + 1,
    }).eq("id", lead_id).execute()

    log_agent("vance", "sequence_run", payload={"lead_id": lead_id, "channel": channel, "score": score})
    return {"ok": True, **result}


# ── Individual Channel Triggers ───────────────────────────────────────────────

@router.post("/leads/{lead_id}/call")
def trigger_call(lead_id: str) -> dict:
    """Force a Vance outbound call for this lead."""
    sb = get_supabase()
    lead = sb.table("leads").select("*").eq("id", lead_id).maybe_single().execute().data
    if not lead:
        raise HTTPException(404, "lead not found")
    from ..agents.vance import start_outbound_call
    result = start_outbound_call(lead)
    sb.table("leads").update({"stage": "contacted", "call_count": (lead.get("call_count") or 0) + 1}).eq("id", lead_id).execute()
    log_agent("vance", "manual_call", payload={"lead_id": lead_id})
    return {"ok": True, "lead_id": lead_id, "call": result}


@router.post("/leads/{lead_id}/sms")
def trigger_sms(lead_id: str, body: dict | None = None) -> dict:
    """Send an outbound SMS to this lead."""
    body = body or {}
    sb = get_supabase()
    lead = sb.table("leads").select("*").eq("id", lead_id).maybe_single().execute().data
    if not lead:
        raise HTTPException(404, "lead not found")
    phone = body.get("phone") or lead.get("phone") or lead.get("owner_phone")
    if not phone:
        raise HTTPException(400, "no phone number on file")
    message = body.get("message") or (
        f"Hi {lead.get('first_name','there')}, 3 Lakes Logistics here — "
        f"we're looking for owner-operators. Reply YES to learn more or STOP to opt out."
    )
    from ..prospecting.sms_compliance import is_opt_out, is_help_request
    if is_opt_out(message):
        return {"ok": False, "reason": "message_triggers_opt_out_detection"}
    from ..agents.signal import _send_sms
    result = _send_sms(phone, message)
    log_agent("vance", "manual_sms", payload={"lead_id": lead_id, "phone": phone})
    return {"ok": True, "lead_id": lead_id, "sms": result}


@router.post("/leads/{lead_id}/nurture")
def enqueue_nurture(lead_id: str, body: dict | None = None) -> dict:
    """Enqueue lead in the 7-email nurture sequence."""
    body = body or {}
    sb = get_supabase()
    lead = sb.table("leads").select("*").eq("id", lead_id).maybe_single().execute().data
    if not lead:
        raise HTTPException(404, "lead not found")
    email = body.get("email") or lead.get("email") or lead.get("owner_email")
    if not email:
        raise HTTPException(400, "no email address on file")

    from ..prospecting.email_nurture import NURTURE_SEQUENCE as sequence
    queued = []
    for step in sequence:
        sb.table("agent_log").insert({
            "agent":   "nova",
            "action":  "nurture_queued",
            "payload": {
                "lead_id":   lead_id,
                "step":      step.get("day"),
                "subject":   step.get("subject"),
                "to_email":  email,
            },
            "result": "queued",
        }).execute()
        queued.append({"day": step.get("day"), "subject": step.get("subject")})

    log_agent("nova", "nurture_enqueued", payload={"lead_id": lead_id, "steps": len(queued)})
    return {"ok": True, "lead_id": lead_id, "nurture_steps_queued": len(queued), "sequence": queued}


# ── Owner Lookup ──────────────────────────────────────────────────────────────

@router.post("/owner-lookup")
def owner_lookup(body: dict) -> dict:
    """Resolve owner contact from DOT number via FMCSA."""
    dot = body.get("dot_number", "")
    if not dot:
        raise HTTPException(400, "dot_number required")
    from ..prospecting.owner_search import find_owner_contact
    contact = find_owner_contact(dot, body.get("company_name", ""))
    if not contact:
        raise HTTPException(404, "owner contact not found")
    return {"ok": True, "contact": contact}


# ── Funnel Stats ──────────────────────────────────────────────────────────────

@router.get("/funnel")
def get_funnel() -> dict:
    """Conversion funnel: new → contacted → demo → signed."""
    from ..prospecting.dashboard import funnel
    return funnel()


# ── On-Demand FMCSA Scrape ────────────────────────────────────────────────────

@router.post("/fmcsa-scrape")
def trigger_fmcsa_scrape(body: dict | None = None) -> dict:
    """Trigger an on-demand FMCSA new-entrant ingest."""
    from ..prospecting.fmcsa_scraper import ingest
    result = ingest()
    log_agent("scout", "fmcsa_scrape_manual", payload=result)
    return {"ok": True, **result}


# ── Vapi Webhook ──────────────────────────────────────────────────────────────

@router.post("/vapi-webhook")
async def vapi_webhook(request: Request) -> dict:
    """Receive Vapi call lifecycle events (call.ended, transcript, recording)."""
    import json
    body = await request.body()
    try:
        event = json.loads(body)
    except Exception:
        raise HTTPException(400, "invalid JSON")
    from ..agents.vance import handle_vapi_event
    handle_vapi_event(event)
    return {"received": True, "type": event.get("type") or event.get("event")}


# ── Nurture ───────────────────────────────────────────────────────────────────

@router.get("/nurture/stats")
def nurture_stats() -> dict:
    """Nurture sequence progress: step distribution and pending count."""
    from datetime import datetime, timezone
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    rows = (
        sb.table("leads")
          .select("id,nurture_step,stage,next_touch_at")
          .in_("stage", ["nurture", "contacted", "new"])
          .eq("do_not_contact", False)
          .execute().data or []
    )
    due = [r for r in rows if r.get("next_touch_at") and r["next_touch_at"] <= now]
    step_dist: dict[int, int] = {}
    for r in rows:
        s = int(r.get("nurture_step") or 0)
        step_dist[s] = step_dist.get(s, 0) + 1
    return {
        "in_sequence": len(rows),
        "due_now": len(due),
        "step_distribution": step_dist,
    }


@router.post("/nurture/run")
def run_nurture_batch() -> dict:
    """Process all leads with a due nurture email."""
    from ..prospecting.email_nurture import run_due_nurtures
    result = run_due_nurtures()
    return {"ok": True, **result}


@router.post("/leads/{lead_id}/nurture-enqueue")
def nurture_enqueue(lead_id: str) -> dict:
    """Put a specific lead into the nurture sequence at step 0."""
    sb = get_supabase()
    lead = sb.table("leads").select("id").eq("id", lead_id).maybe_single().execute().data
    if not lead:
        raise HTTPException(404, "lead not found")
    from ..prospecting.email_nurture import enqueue_lead
    enqueue_lead(lead_id)
    return {"ok": True, "lead_id": lead_id, "stage": "nurture"}


# ── Referral Loop ─────────────────────────────────────────────────────────────

@router.post("/referrals/run")
def run_referral_batch(body: dict | None = None) -> dict:
    """Send referral-ask SMS to dead leads (up to 50)."""
    body = body or {}
    limit = int(body.get("limit", 50))
    from ..prospecting.referral_loop import request_referrals
    result = request_referrals(limit=limit)
    return {"ok": True, **result}


# ── Social Listener ───────────────────────────────────────────────────────────

@router.post("/social-scan")
def social_scan(body: dict | None = None) -> dict:
    """Scan Reddit for owner-op/dispatch signal keywords and ingest as leads."""
    body = body or {}
    limit = int(body.get("limit", 25))
    from ..prospecting.social_listener import ingest_signals
    result = ingest_signals(limit=limit)
    log_agent("scout", "social_scan_manual", payload=result)
    return {"ok": True, **result}


# ── TruckPaper Scrape ─────────────────────────────────────────────────────────

@router.post("/truckpaper-scrape")
def truckpaper_scrape(body: dict | None = None) -> dict:
    """Scrape TruckPaper listings for prospective owner-operators."""
    body = body or {}
    states = body.get("states")
    equipment = body.get("equipment", "dry_van")
    from ..prospecting.truckpaper_scraper import ingest
    result = ingest(states=states, equipment=equipment)
    log_agent("scout", "truckpaper_scrape_manual", payload=result)
    return {"ok": True, **result}

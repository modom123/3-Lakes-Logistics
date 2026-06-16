"""Prospecting pipeline — sources leads, scores them, optionally triggers Vance calls.

POST /api/prospecting/run   — kick off a pipeline run
GET  /api/prospecting/status — latest run summary from agent_log
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from ..agents import vance as vance_agent
from ..logging_service import log_agent
from ..prospecting import dedupe, scoring
from ..settings import get_settings
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


# ── helpers ──────────────────────────────────────────────────────────────────

def _seed_demo_leads(limit: int) -> list[dict[str, Any]]:
    """Return realistic-looking demo leads when FMCSA key is not configured."""
    import random, time
    companies = [
        ("Midwest Express Freight", "MI", "dry_van", "313"),
        ("South Star Transport", "GA", "reefer", "404"),
        ("Lone Star Carriers", "TX", "flatbed", "214"),
        ("Great Lakes Hauling", "OH", "dry_van", "216"),
        ("Carolina Road Kings", "NC", "step_deck", "704"),
        ("Desert Wind Logistics", "AZ", "dry_van", "602"),
        ("Keystone Fleet", "PA", "reefer", "215"),
        ("Rocky Mountain Transport", "CO", "flatbed", "720"),
        ("Gulf Coast Moving", "LA", "dry_van", "504"),
        ("Appalachian Freight", "TN", "box26", "615"),
        ("Prairie Wind Carriers", "KS", "dry_van", "316"),
        ("Pacific Coast Movers", "CA", "reefer", "213"),
        ("Bluegrass Trucking", "KY", "dry_van", "502"),
        ("River Valley Logistics", "MO", "flatbed", "314"),
        ("Heartland Express LLC", "IA", "dry_van", "515"),
        ("Mountain State Freight", "WV", "box26", "304"),
        ("Bayou Haulers", "MS", "dry_van", "601"),
        ("Tarheel Transport", "NC", "reefer", "919"),
        ("Steel City Carriers", "PA", "flatbed", "412"),
        ("Sunrise Fleet Services", "FL", "dry_van", "305"),
    ]
    random.seed(int(time.time() / 3600))
    chosen = random.sample(companies, min(limit, len(companies)))
    leads = []
    for i, (name, state, equip, area) in enumerate(chosen):
        fleet = random.choice([1, 1, 1, 2, 2, 3, 4, 5])
        dot_age = random.randint(15, 200)
        has_phone = random.random() > 0.15
        has_email = random.random() > 0.4
        dot = str(random.randint(3000000, 4200000))
        mc = str(random.randint(800000, 1200000)) if random.random() > 0.25 else None
        lead: dict[str, Any] = {
            "source": "fmcsa_demo",
            "source_ref": dot,
            "company_name": name,
            "dot_number": dot,
            "mc_number": mc,
            "phone": f"({area}) {random.randint(200,999)}-{random.randint(1000,9999)}" if has_phone else None,
            "email": f"dispatch@{name.lower().replace(' ', '')}.com" if has_email else None,
            "address": f"123 Main St, {state} {random.randint(10000,99999)}",
            "fleet_size": fleet,
            "equipment_types": [equip],
            "dot_age_days": dot_age,
            "stage": "new",
        }
        lead["score"] = scoring.score_lead(lead)
        leads.append(lead)
    return leads


def _run_fmcsa_ingest(since_days: int = 1) -> list[dict[str, Any]]:
    """Pull real carrier leads from the DOT/FMCSA census dataset via Naomi's pipeline.

    The old SAFER new-entrant endpoint was never implemented (stub returned []).
    Naomi's DOT open-data approach is the real, working FMCSA integration.
    """
    from ..agents.naomi import _pull_fmcsa_prospects, _get_hot_states
    hot_states = _get_hot_states(top_n=5)
    if not hot_states:
        # Fallback to always-useful high-volume states
        hot_states = {"TX": 1.3, "FL": 1.2, "CA": 1.2, "OH": 1.1, "GA": 1.1}
    prospects = _pull_fmcsa_prospects(hot_states, per_state=40)
    # Convert to route_prospecting format (already scored by naomi)
    for p in prospects:
        if "score" not in p or not p["score"]:
            p["score"] = scoring.score_lead(p)
    return prospects


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/run")
def run_pipeline(
    source: str = "auto",          # "fmcsa" | "demo" | "auto"
    min_score: int = 6,
    limit: int = 20,
    auto_call: bool = False,
) -> dict:
    """
    Source leads → score → insert qualifying rows → optionally trigger Vance.

    Returns a run summary immediately; Vance calls fire async via Vapi.
    """
    s = get_settings()
    sb = get_supabase()
    started_at = datetime.now(timezone.utc).isoformat()

    # 1. Source leads — try real FMCSA data first; fall back to demo only if needed
    actual_source = "demo"
    if source == "demo":
        raw_leads = _seed_demo_leads(limit)
    else:
        # Try real FMCSA (public DOT Socrata API — works without a key)
        raw_leads = _run_fmcsa_ingest()
        if raw_leads:
            actual_source = "fmcsa"
        else:
            raw_leads = _seed_demo_leads(limit)
    raw_leads = raw_leads[:limit]

    log_agent("sonny", "pipeline_source",
              payload={"source": actual_source, "count": len(raw_leads)},
              result=f"sourced {len(raw_leads)} from {actual_source}")

    # 2. Dedupe + insert qualifying leads
    inserted, skipped, calls_queued = 0, 0, 0
    call_results: list[dict] = []

    for lead in raw_leads:
        if lead["score"] < min_score:
            skipped += 1
            continue
        if dedupe.is_duplicate(lead.get("dot_number"), lead.get("mc_number")):
            skipped += 1
            continue

        res = sb.table("leads").insert(lead).execute()
        inserted += 1

        # 3. Optionally trigger Vance for high-scoring leads with a phone
        if auto_call and lead.get("phone") and lead["score"] >= 8:
            lead_id = (res.data or [{}])[0].get("id", "")
            call_res = vance_agent.run({
                "lead_id": lead_id,
                "phone": lead["phone"],
                "prospect_name": lead.get("company_name", "Friend"),
                "company_name": lead.get("company_name", ""),
                "dot_number": lead.get("dot_number", ""),
            })
            calls_queued += 1
            call_results.append({"lead": lead.get("company_name"), **call_res})

    log_agent("atlas", "pipeline_complete",
              payload={"inserted": inserted, "skipped": skipped, "calls": calls_queued},
              result=f"{inserted} new leads, {calls_queued} calls queued")

    return {
        "ok": True,
        "started_at": started_at,
        "source": actual_source,
        "sourced": len(raw_leads),
        "inserted": inserted,
        "skipped_low_score_or_dupe": skipped,
        "calls_queued": calls_queued,
        "call_results": call_results,
        "min_score_used": min_score,
        "bland_configured": bool(s.bland_ai_api_key),
"fmcsa_configured": bool(s.fmcsa_webkey),
    }


@router.get("/status")
def pipeline_status() -> dict:
    """Return recent pipeline run entries from agent_log."""
    sb = get_supabase()
    rows = (
        sb.table("agent_log")
        .select("*")
        .in_("agent", ["sonny", "atlas"])
        .in_("action", ["pipeline_source", "pipeline_complete", "fmcsa_ingest"])
        .order("ts", desc=True)
        .limit(10)
        .execute()
    ).data or []
    return {"runs": rows}


@router.post("/call")
def manual_call(body: dict) -> dict:
    """Trigger a single Vance outbound call from EAGLE EYE.

    Body: { name, phone, company?, notes? }
    """
    name  = (body.get("name") or "").strip()
    phone = (body.get("phone") or "").strip()
    if not phone:
        from fastapi import HTTPException
        raise HTTPException(400, "phone is required")

    # Normalise to E.164 — strip spaces/dashes/parens, prepend +1 if needed
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        digits = "1" + digits
    e164 = "+" + digits

    lead_id = f"manual-{name.lower().replace(' ','-')}-{digits[-4:]}"
    result = vance_agent.run({
        "phone":         e164,
        "name":          name or "there",
        "company_name":  body.get("company", ""),
        "current_pain":  body.get("notes", ""),
        "lead_id":       lead_id,
    })

    log_agent("vance", "manual_call", payload={"name": name, "phone": e164}, result=result.get("status"))
    return {"ok": result.get("status") == "started", "call_id": result.get("call_id"), "phone": e164, "name": name, "result": result}


@router.get("/calls")
def recent_calls(limit: int = 25) -> dict:
    """Recent manual + pipeline Vance calls from agent_log."""
    sb = get_supabase()
    rows = (
        sb.table("agent_log")
        .select("*")
        .eq("agent", "vance")
        .order("ts", desc=True)
        .limit(limit)
        .execute()
    ).data or []
    return {"calls": rows}


@router.post("/run-machine")
def run_full_machine(
    source: str = "auto",
    min_score: int = 7,
    limit: int = 20,
    auto_call: bool = True,
    auto_onboard: bool = True,
) -> dict:
    """
    End-to-end carrier acquisition pipeline:
    1. Source leads from FMCSA (or demo)
    2. Score every lead with AI scoring model
    3. Insert qualifying leads into the database
    4. Auto-call score >= 8 leads via Vance / Bland AI
    5. Detect any existing Won/Converted leads without a carrier record
    6. Create carrier records for Won leads and fire onboarding workflow
    """
    from ..triggers import fire_onboarding
    s = get_settings()
    sb = get_supabase()
    started_at = datetime.now(timezone.utc).isoformat()
    machine_log: list[dict] = []

    def _log(stage: str, msg: str, data: dict | None = None):
        entry = {"stage": stage, "msg": msg, "ts": datetime.now(timezone.utc).isoformat(), **(data or {})}
        machine_log.append(entry)
        log_agent("machine", f"machine.{stage}", payload=data or {}, result=msg)

    # ── Stage 1: Source leads — try real FMCSA first, fall back to demo ──────────
    _log("source", f"Sourcing leads…")
    if source == "demo":
        raw_leads = _seed_demo_leads(limit)
        actual_source = "demo"
    else:
        raw_leads = _run_fmcsa_ingest()
        if raw_leads:
            actual_source = "fmcsa"
        else:
            raw_leads = _seed_demo_leads(limit)
            actual_source = "demo"
    raw_leads = raw_leads[:limit]
    _log("source", f"Sourced {len(raw_leads)} candidates from {actual_source}", {"count": len(raw_leads), "source": actual_source})

    # ── Stage 2: Score + insert qualifying leads ───────────────────────────────
    _log("score", f"Scoring {len(raw_leads)} candidates (min score {min_score})…")
    inserted, skipped_score, skipped_dupe = 0, 0, 0
    new_lead_ids: list[str] = []

    for lead in raw_leads:
        if not lead.get("score"):
            lead["score"] = scoring.score_lead(lead)
        if lead["score"] < min_score:
            skipped_score += 1
            continue
        if dedupe.is_duplicate(lead.get("dot_number"), lead.get("mc_number")):
            skipped_dupe += 1
            continue
        res = sb.table("leads").insert({**lead, "stage": "new", "status": "new"}).execute()
        lead_id = (res.data or [{}])[0].get("id", "")
        if lead_id:
            new_lead_ids.append(lead_id)
            lead["_id"] = lead_id
        inserted += 1

    _log("score", f"Inserted {inserted} new leads ({skipped_score} below score, {skipped_dupe} duplicates)",
         {"inserted": inserted, "skipped_score": skipped_score, "skipped_dupe": skipped_dupe})

    # ── Stage 3: Vance auto-calls for score >= 8 leads ────────────────────────
    calls_queued, call_results = 0, []
    if auto_call:
        callable_leads = [l for l in raw_leads if l.get("_id") and l.get("phone") and l.get("score", 0) >= 8]
        _log("call", f"Queueing Vance calls for {len(callable_leads)} high-score leads…")
        for lead in callable_leads:
            call_res = vance_agent.run({
                "lead_id": lead["_id"],
                "phone": lead["phone"],
                "prospect_name": lead.get("company_name", "Friend"),
                "company_name": lead.get("company_name", ""),
                "dot_number": lead.get("dot_number", ""),
                "score": lead.get("score"),
            })
            calls_queued += 1
            call_results.append({"lead": lead.get("company_name"), "status": call_res.get("status"), "call_id": call_res.get("call_id")})
        _log("call", f"{calls_queued} calls queued via Bland AI / Vance",
             {"calls_queued": calls_queued, "bland_configured": bool(s.bland_ai_api_key)})
    else:
        _log("call", "Auto-call disabled — leads queued for manual outreach")

    # ── Stage 4: Detect Won/Converted leads → auto-onboarding ─────────────────
    onboarded, onboard_results = 0, []
    if auto_onboard:
        _log("onboard", "Scanning for Won/Converted leads to auto-onboard…")
        won_leads = (
            sb.table("leads")
            .select("id, business_name, company_name, dot_number, mc_number, phone, email, converted_carrier_id")
            .in_("status", ["won", "Won", "converted", "Converted"])
            .is_("converted_carrier_id", None)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        ).data or []

        for lead in won_leads:
            name = lead.get("business_name") or lead.get("company_name") or "Unknown Carrier"
            try:
                # Create carrier record
                carrier_data = {
                    "name": name,
                    "dot_number": lead.get("dot_number"),
                    "mc_number": lead.get("mc_number"),
                    "phone": lead.get("phone"),
                    "email": lead.get("email"),
                    "status": "Onboarding",
                    "source": "machine_pipeline",
                }
                carrier_res = sb.table("carriers").insert(carrier_data).execute()
                carrier_id = (carrier_res.data or [{}])[0].get("id", "")
                if carrier_id:
                    # Link carrier back to lead
                    sb.table("leads").update({"converted_carrier_id": carrier_id}).eq("id", lead["id"]).execute()
                    # Fire onboarding domain
                    import threading
                    threading.Thread(target=fire_onboarding, args=(carrier_id,), daemon=True).start()
                    onboarded += 1
                    onboard_results.append({"carrier": name, "carrier_id": carrier_id, "status": "onboarding_fired"})
                    _log("onboard", f"Onboarding fired for {name}", {"carrier_id": carrier_id})
            except Exception as exc:
                _log("onboard", f"Failed to onboard {name}: {exc}")

        if not won_leads:
            _log("onboard", "No unconverted Won leads found — onboarding queue is clear")

    # ── Final summary ──────────────────────────────────────────────────────────
    completed_at = datetime.now(timezone.utc).isoformat()
    log_agent("machine", "machine.complete", payload={
        "sourced": len(raw_leads), "inserted": inserted,
        "calls": calls_queued, "onboarded": onboarded,
    }, result=f"Machine complete: {inserted} leads, {calls_queued} calls, {onboarded} onboarded")

    return {
        "ok": True,
        "started_at": started_at,
        "completed_at": completed_at,
        "source": actual_source,
        "stages": {
            "sourced": len(raw_leads),
            "inserted": inserted,
            "skipped_score": skipped_score,
            "skipped_dupe": skipped_dupe,
            "calls_queued": calls_queued,
            "onboarded": onboarded,
        },
        "call_results": call_results,
        "onboard_results": onboard_results,
        "machine_log": machine_log,
        "bland_configured": bool(s.bland_ai_api_key),
        "fmcsa_configured": bool(s.fmcsa_webkey),
    }


@router.get("/machine-status")
def machine_status() -> dict:
    """Return live pipeline counts and recent machine activity."""
    sb = get_supabase()
    # Lead funnel counts
    leads = (sb.table("leads").select("status, stage, score, created_at").limit(2000).execute()).data or []
    today = datetime.now(timezone.utc).date().isoformat()
    stg = lambda l: (l.get("status") or l.get("stage") or "new").lower()
    funnel = {
        "new":          sum(1 for l in leads if stg(l) == "new"),
        "contacted":    sum(1 for l in leads if stg(l) == "contacted"),
        "interested":   sum(1 for l in leads if stg(l) in ("interested", "qualified")),
        "not_interested": sum(1 for l in leads if stg(l) == "not_interested"),
        "won":          sum(1 for l in leads if stg(l) in ("won", "converted")),
        "total":        len(leads),
        "sourced_today": sum(1 for l in leads if (l.get("created_at") or "")[:10] == today),
    }
    # Recent machine + agent activity
    activity = (
        sb.table("agent_log")
        .select("agent, action, result, ts, payload")
        .in_("agent", ["machine", "sonny", "vance", "naomi", "alexander", "atlas", "isabella", "echo"])
        .order("ts", desc=True)
        .limit(30)
        .execute()
    ).data or []
    # Recent onboarding triggers
    onboarding = (
        sb.table("agent_log")
        .select("agent, action, result, ts, payload")
        .eq("action", "trigger.onboarding")
        .order("ts", desc=True)
        .limit(10)
        .execute()
    ).data or []
    return {"funnel": funnel, "activity": activity, "onboarding": onboarding}


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


def _run_fmcsa_ingest(limit: int = 50) -> list[dict[str, Any]]:
    """Pull real new-entrant leads from FMCSA Census (no API key needed)."""
    from ..prospecting.fmcsa_scraper import fetch_new_entrants, today_state
    from ..prospecting import scoring

    records = fetch_new_entrants(limit=limit)
    leads = []
    for rec in records:
        dot = str(rec.get("dot_number") or "").strip()
        mc_raw = rec.get("mc_mx_ff_number") or ""
        mc = mc_raw.replace("MC-", "").replace("MX-", "").replace("FF-", "").strip()
        name = (rec.get("legal_name") or rec.get("dba_name") or "").strip()
        if not name:
            continue

        def _int(v: Any) -> int:
            try:
                return int(str(v or 0).replace(",", ""))
            except (ValueError, TypeError):
                return 0

        trucks   = _int(rec.get("total_power_units"))
        tractors = _int(rec.get("tractor_trucks"))
        straight = _int(rec.get("straight_trucks"))
        equip_types = []
        if tractors > 0:
            equip_types.append("Tractor-Trailer")
        if straight > 0:
            equip_types.append("Straight Truck")
        if rec.get("hm_flag") == "Y":
            equip_types.append("Hazmat")

        rating = (rec.get("safety_rating") or "Not Rated").strip()
        notes_parts = [f"FMCSA Safety Rating: {rating}"]
        if trucks:
            notes_parts.append(f"Trucks: {trucks}")
        if rec.get("total_drivers"):
            notes_parts.append(f"Drivers: {rec['total_drivers']}")
        op = {"I": "Interstate", "A": "Intrastate", "H": "Intrastate HM"}.get(
            rec.get("carrier_operation", ""), ""
        )
        if op:
            notes_parts.append(f"Op: {op}")
        if rec.get("add_date"):
            notes_parts.append(f"DOT registered: {str(rec['add_date'])[:10]}")

        lead: dict[str, Any] = {
            "business_name": name,
            "company_name":  name,
            "source":        "FMCSA",
            "source_ref":    dot,
            "status":        "New",
            "stage":         "new",
            "notes":         " · ".join(notes_parts),
        }
        if dot:                     lead["dot_number"]     = dot
        if mc:                      lead["mc_number"]      = mc
        if rec.get("telephone"):    lead["phone"]          = str(rec["telephone"]).strip()
        if rec.get("phy_city"):     lead["city"]           = str(rec["phy_city"]).strip()
        if rec.get("phy_state"):    lead["state"]          = str(rec["phy_state"]).strip()
        if trucks:                  lead["fleet_size"]     = trucks
        if equip_types:             lead["equipment_type"] = equip_types[0]
        if equip_types:             lead["equipment_types"] = equip_types

        lead["score"] = scoring.score_lead(lead)
        leads.append(lead)

    return leads


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/run")
def run_pipeline(
    source: str = "auto",   # "fmcsa" | "demo" | "auto"
    min_score: int = 6,
    limit: int = 50,        # default 50 leads per run
    auto_call: bool = False,
) -> dict:
    """
    Source leads → score → insert qualifying rows → optionally trigger Vance.

    Returns a run summary immediately; Vance calls fire async via Vapi.
    FMCSA source works without any API key — uses open Census dataset.
    """
    s = get_settings()
    sb = get_supabase()
    started_at = datetime.now(timezone.utc).isoformat()

    # 1. Source leads — FMCSA Census works without a key; demo only for explicit request
    use_demo = source == "demo"
    raw_leads = _seed_demo_leads(limit) if use_demo else _run_fmcsa_ingest(limit)
    raw_leads = raw_leads[:limit]

    log_agent("sonny", "pipeline_source",
              payload={"source": "demo" if use_demo else "fmcsa", "count": len(raw_leads)},
              result=f"sourced {len(raw_leads)}")

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

    from ..prospecting.fmcsa_scraper import today_state
    return {
        "ok": True,
        "started_at": started_at,
        "source": "demo" if use_demo else "fmcsa",
        "sourced": len(raw_leads),
        "inserted": inserted,
        "skipped_low_score_or_dupe": skipped,
        "calls_queued": calls_queued,
        "call_results": call_results,
        "min_score_used": min_score,
        "state_targeted": today_state(),
        "fmcsa_configured": True,   # open Census API — no key needed
        "bland_configured": bool(s.bland_ai_api_key),
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


@router.post("/daily")
def daily_pull(
    min_score: int = 6,
    auto_call: bool = False,
) -> dict:
    """Daily automated 50-lead pull from FMCSA Census.

    Designed to be called by a cron job or the Eagle Eye "Daily Pull" button.
    Always pulls exactly 50 leads from today's target state, dedupes, scores,
    and inserts qualifying leads. No API key required.
    """
    from ..prospecting.fmcsa_scraper import today_state
    return run_pipeline(source="fmcsa", min_score=min_score, limit=50, auto_call=auto_call)


@router.get("/daily-status")
def daily_status() -> dict:
    """Return today's pull summary and the target state for each upcoming day."""
    from ..prospecting.fmcsa_scraper import _STATES, today_state
    from datetime import date

    sb = get_supabase()

    # Last daily pull log entry
    last_run = (
        sb.table("agent_log")
        .select("ts, result, payload")
        .eq("agent", "vance")
        .eq("action", "fmcsa_ingest")
        .order("ts", desc=True)
        .limit(1)
        .execute()
    ).data or []

    # Today's lead count from FMCSA source
    today_str = date.today().isoformat()
    today_count_res = (
        sb.table("leads")
        .select("id", count="exact")
        .eq("source", "FMCSA")
        .gte("created_at", today_str)
        .execute()
    )
    today_count = today_count_res.count or 0

    # Next 7 days' state schedule
    today_idx = datetime.now(timezone.utc).timetuple().tm_yday
    schedule = []
    for offset in range(7):
        d = datetime.now(timezone.utc).date() + timedelta(days=offset)
        state = _STATES[(today_idx + offset) % len(_STATES)]
        schedule.append({"date": d.isoformat(), "state": state, "is_today": offset == 0})

    return {
        "today_state": today_state(),
        "today_leads_pulled": today_count,
        "last_run": last_run[0] if last_run else None,
        "upcoming_states": schedule,
    }

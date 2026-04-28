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
    """Pull real new-entrant leads from FMCSA if key is configured."""
    from ..prospecting.fmcsa_scraper import fetch_new_entrants
    raw = fetch_new_entrants(since_days)
    leads = []
    for e in raw:
        dot = str(e.get("dotNumber") or "")
        mc = str(e.get("docketNumber") or "")
        lead: dict[str, Any] = {
            "source": "fmcsa",
            "source_ref": dot,
            "company_name": e.get("legalName"),
            "dot_number": dot,
            "mc_number": mc or None,
            "phone": e.get("phone"),
            "email": e.get("emailAddress"),
            "address": e.get("physicalAddress"),
            "fleet_size": e.get("totalPowerUnits"),
            "equipment_types": [],
            "stage": "new",
        }
        lead["score"] = scoring.score_lead(lead)
        leads.append(lead)
    return leads


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

    # 1. Source leads
    use_demo = source == "demo" or (source == "auto" and not s.fmcsa_webkey)
    raw_leads = _seed_demo_leads(limit) if use_demo else _run_fmcsa_ingest()
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
            call_res = vance_agent.start_outbound_call(
                lead_id=lead_id,
                phone=lead["phone"],
                script_vars={
                    "company_name": lead.get("company_name", ""),
                    "equipment_types": lead.get("equipment_types", []),
                },
            )
            calls_queued += 1
            call_results.append({"lead": lead.get("company_name"), **call_res})

    log_agent("atlas", "pipeline_complete",
              payload={"inserted": inserted, "skipped": skipped, "calls": calls_queued},
              result=f"{inserted} new leads, {calls_queued} calls queued")

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
        "vapi_configured": bool(s.vapi_api_key and s.vapi_assistant_id_vance),
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

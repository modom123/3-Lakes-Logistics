"""Leads — powers the command center `Leads` page and Vance outbound."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..models.lead import Lead
from ..prospecting import dedupe, scoring
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.get("/")
def list_leads(
    stage: str | None = None,
    source: str | None = None,
    min_score: int = 0,
    limit: int = 500,
) -> dict:
    q = get_supabase().table("leads").select("*").order("score", desc=True).limit(limit)
    if stage:
        q = q.eq("stage", stage)
    if source:
        q = q.eq("source", source)
    if min_score:
        q = q.gte("score", min_score)
    res = q.execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.post("/")
def create_lead(lead: Lead) -> dict:
    if dedupe.is_duplicate(lead.dot_number, lead.mc_number):
        raise HTTPException(409, "duplicate lead")
    data = lead.model_dump(exclude_none=True)
    data["score"] = scoring.score_lead(data)
    res = get_supabase().table("leads").insert(data).execute()
    return {"ok": True, "lead": (res.data or [None])[0]}


@router.get("/{lead_id}")
def get_lead(lead_id: str) -> dict:
    res = get_supabase().table("leads").select("*").eq("id", lead_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "lead not found")
    return res.data


@router.patch("/{lead_id}")
def update_lead(lead_id: str, patch: dict) -> dict:
    get_supabase().table("leads").update(patch).eq("id", lead_id).execute()
    return {"ok": True}


_VALID_STAGES = {"new", "contacted", "interested", "demo_scheduled", "negotiating",
                 "converted", "lost", "disqualified"}


@router.patch("/{lead_id}/stage")
def set_stage(lead_id: str, stage: str) -> dict:
    """Move lead through the sales funnel."""
    if stage not in _VALID_STAGES:
        raise HTTPException(400, f"stage must be one of {sorted(_VALID_STAGES)}")
    get_supabase().table("leads").update({"stage": stage}).eq("id", lead_id).execute()
    return {"ok": True, "lead_id": lead_id, "stage": stage}


@router.post("/{lead_id}/call")
def trigger_outbound_call(lead_id: str, body: dict | None = None) -> dict:
    """Trigger a Vapi outbound call to this lead via the Vance agent."""
    res = get_supabase().table("leads").select("*").eq("id", lead_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "lead not found")
    lead = res.data

    from ..agents.vance import start_outbound_call
    body = body or {}
    result = start_outbound_call(
        lead_id=lead_id,
        phone=lead.get("phone") or body.get("phone", ""),
        script_vars={
            "company_name": lead.get("company_name", ""),
            "contact_name": lead.get("contact_name", ""),
            "fleet_size": lead.get("fleet_size", ""),
            **body,
        },
    )
    if result.get("status") == "started":
        get_supabase().table("leads").update({"stage": "contacted"}).eq("id", lead_id).execute()
    return {"ok": True, "lead_id": lead_id, "call": result}


@router.post("/{lead_id}/score")
def rescore_lead(lead_id: str) -> dict:
    """Recalculate and update the lead score."""
    res = get_supabase().table("leads").select("*").eq("id", lead_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "lead not found")
    new_score = scoring.score_lead(res.data)
    get_supabase().table("leads").update({"score": new_score}).eq("id", lead_id).execute()
    return {"ok": True, "lead_id": lead_id, "score": new_score}

"""Leads — powers the EAGLE EYE `Leads` page and Vance outbound."""
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
    sb = get_supabase()
    q = sb.table("leads").select("*").order("score", desc=True).limit(limit)
    # live table uses 'status' column; support both filter param names
    if stage:
        q = q.eq("status", stage)
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
    # Map to live table column names
    if "company_name" in data and "business_name" not in data:
        data["business_name"] = data.pop("company_name")
    if "stage" in data and "status" not in data:
        data["status"] = data.pop("stage")
    res = get_supabase().table("leads").insert(data).execute()
    return {"ok": True, "lead": (res.data or [None])[0]}


@router.patch("/{lead_id}")
def update_lead(lead_id: str, patch: dict) -> dict:
    # Remap column names if caller uses old names
    if "company_name" in patch and "business_name" not in patch:
        patch["business_name"] = patch.pop("company_name")
    if "stage" in patch and "status" not in patch:
        patch["status"] = patch.pop("stage")
    get_supabase().table("leads").update(patch).eq("id", lead_id).execute()
    return {"ok": True}

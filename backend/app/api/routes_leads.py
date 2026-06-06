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
    # Filter by either stage or status column (both exist after migration 018)
    if stage:
        q = q.eq("stage", stage)
    if source:
        q = q.eq("source", source)
    if min_score:
        q = q.gte("score", min_score)
    try:
        res = q.execute()
    except Exception as exc:
        raise HTTPException(500, f"Database error loading leads: {exc}") from exc
    return {"count": len(res.data or []), "items": res.data or []}


@router.post("/")
def create_lead(lead: Lead) -> dict:
    if dedupe.is_duplicate(lead.dot_number, lead.mc_number):
        raise HTTPException(409, "duplicate lead")
    data = lead.model_dump(exclude_none=True)
    data["score"] = scoring.score_lead(data)
    # Keep both company_name and business_name populated for compatibility
    if data.get("business_name") and not data.get("company_name"):
        data["company_name"] = data["business_name"]
    if data.get("company_name") and not data.get("business_name"):
        data["business_name"] = data["company_name"]
    # Keep both stage and status populated for compatibility
    if data.get("stage") and not data.get("status"):
        data["status"] = data["stage"]
    if data.get("status") and not data.get("stage"):
        data["stage"] = data["status"]
    # Ensure a display name exists
    if not data.get("company_name") and not data.get("business_name"):
        name = data.get("contact_name") or data.get("source_ref") or "Unknown"
        data["company_name"] = name
        data["business_name"] = name
    try:
        res = get_supabase().table("leads").insert(data).execute()
    except Exception as exc:
        raise HTTPException(500, f"Database error creating lead: {exc}") from exc
    return {"ok": True, "lead": (res.data or [None])[0]}


@router.patch("/{lead_id}")
def update_lead(lead_id: str, patch: dict) -> dict:
    # Keep both column-name variants in sync
    if "company_name" in patch and "business_name" not in patch:
        patch["business_name"] = patch["company_name"]
    if "business_name" in patch and "company_name" not in patch:
        patch["company_name"] = patch["business_name"]
    if "stage" in patch and "status" not in patch:
        patch["status"] = patch["stage"]
    if "status" in patch and "stage" not in patch:
        patch["stage"] = patch["status"]
    try:
        get_supabase().table("leads").update(patch).eq("id", lead_id).execute()
    except Exception as exc:
        raise HTTPException(500, f"Database error updating lead: {exc}") from exc
    return {"ok": True}

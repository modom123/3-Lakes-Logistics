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


@router.get("/{lead_id}/score")
def explain_score(lead_id: str) -> dict:
    """Return a detailed score breakdown for a single lead."""
    from ..prospecting.scoring import score_summary
    res = get_supabase().table("leads").select("*").eq("id", lead_id).limit(1).execute()
    lead = (res.data or [None])[0]
    if not lead:
        raise HTTPException(404, "Lead not found")
    return score_summary(lead)


@router.post("/rescore")
def rescore_all_leads(min_score: int = 0) -> dict:
    """Re-score every lead in the database with the current scoring model.

    Use after a scoring model update to refresh all scores.
    Returns counts of leads updated and how many changed.
    """
    from ..prospecting.scoring import score_lead
    sb = get_supabase()
    leads = sb.table("leads").select("id, score, safety_rating, operating_status, oos_date, phone, email, fleet_size, total_power_units, mc_number, dot_age_days, add_date, mcs150_date, equipment_types, company_name, business_name, legal_name, contact_name").limit(2000).execute().data or []
    updated, changed = 0, 0
    for lead in leads:
        new_score = score_lead(lead)
        if new_score != (lead.get("score") or 0):
            sb.table("leads").update({"score": new_score}).eq("id", lead["id"]).execute()
            changed += 1
        updated += 1
    return {"ok": True, "total": updated, "rescored": changed, "unchanged": updated - changed}


@router.get("/outreach-log")
def outreach_log(limit: int = 20) -> dict:
    """Return recent SMS/email outreach activity logged against leads."""
    sb = get_supabase()
    try:
        rows = (
            sb.table("agent_log")
            .select("agent, action, result, ts, payload")
            .in_("action", ["sms_sent", "email_sent", "sms_blast", "email_blast"])
            .order("ts", desc=True)
            .limit(limit)
            .execute()
        ).data or []
        items = [
            {
                "type": "sms" if "sms" in (r.get("action") or "") else "email",
                "lead_name": (r.get("payload") or {}).get("lead_name") or (r.get("payload") or {}).get("name") or "Lead",
                "message": r.get("result") or "",
                "sent_at": r.get("ts"),
            }
            for r in rows
        ]
    except Exception:
        items = []
    return {"ok": True, "items": items}


@router.post("/sms-blast")
def sms_blast(body: dict) -> dict:
    """Queue an SMS to a list of leads. Logs the campaign; delivery requires Twilio."""
    from ..logging_service import log_agent
    lead_ids = body.get("lead_ids") or []
    message = body.get("message") or ""
    if not lead_ids or not message:
        raise HTTPException(400, "lead_ids and message are required")
    log_agent("isabella", "sms_blast",
              payload={"count": len(lead_ids), "message_preview": message[:80]},
              result=f"SMS queued for {len(lead_ids)} leads")
    return {"ok": True, "sent": len(lead_ids), "queued": len(lead_ids)}


@router.post("/email-blast")
def email_blast(body: dict) -> dict:
    """Queue an email to a list of leads. Logs the campaign; delivery requires SendGrid/Mailgun."""
    from ..logging_service import log_agent
    lead_ids = body.get("lead_ids") or []
    subject = body.get("subject") or ""
    email_body = body.get("body") or ""
    if not lead_ids or not subject:
        raise HTTPException(400, "lead_ids and subject are required")
    log_agent("echo", "email_blast",
              payload={"count": len(lead_ids), "subject": subject},
              result=f"Email queued for {len(lead_ids)} leads — subject: {subject[:60]}")
    return {"ok": True, "sent": len(lead_ids), "queued": len(lead_ids)}

"""Leads — powers the EAGLE EYE `Leads` page and Vance outbound."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..models.lead import Lead
from ..prospecting import dedupe, scoring
from ..prospecting.activity import log_activity
from ..settings import get_settings
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
    if stage:
        q = q.eq("status", stage)
    if source:
        q = q.eq("source", source)
    if min_score:
        q = q.gte("score", min_score)
    res = q.execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.get("/{lead_id}")
def get_lead(lead_id: str) -> dict:
    sb = get_supabase()
    row = sb.table("leads").select("*").eq("id", lead_id).maybe_single().execute()
    if not row.data:
        raise HTTPException(404, "lead not found")
    return row.data


@router.get("/{lead_id}/activities")
def get_activities(lead_id: str, limit: int = 50) -> dict:
    sb = get_supabase()
    rows = (
        sb.table("lead_activities")
        .select("*")
        .eq("lead_id", lead_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    ).data or []
    return {"lead_id": lead_id, "count": len(rows), "activities": rows}


@router.post("/{lead_id}/activities")
def add_activity(lead_id: str, body: dict) -> dict:
    channel = body.get("channel", "note")
    status  = body.get("status", "sent")
    summary = body.get("summary", "")
    agent   = body.get("agent", "manual")
    payload = body.get("payload", {})
    log_activity(lead_id, channel, status, summary=summary, agent=agent, payload=payload)
    return {"ok": True}


@router.post("/{lead_id}/call")
def trigger_call(lead_id: str) -> dict:
    sb = get_supabase()
    lead = sb.table("leads").select("*").eq("id", lead_id).maybe_single().execute()
    if not lead.data:
        raise HTTPException(404, "lead not found")
    l = lead.data
    phone = (l.get("phone") or "").strip()
    if not phone:
        raise HTTPException(400, "lead has no phone number")

    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        digits = "1" + digits
    e164 = "+" + digits

    from ..agents import vance as vance_agent
    result = vance_agent.run({
        "lead_id":       lead_id,
        "phone":         e164,
        "prospect_name": l.get("business_name") or l.get("company_name") or "there",
        "prospect_email": l.get("email") or "",
        "company_name":  l.get("business_name") or l.get("company_name") or "",
        "dot_number":    l.get("dot_number") or "",
    })

    status = "sent" if result.get("status") == "started" else "error"
    log_activity(lead_id, "call", status,
                 summary="Outbound call via Vance (Bland AI)",
                 agent="vance",
                 payload={"call_id": result.get("call_id"), "phone": e164})
    return {"ok": status == "sent", "phone": e164, "result": result}


@router.post("/{lead_id}/sms")
def send_sms(lead_id: str, body: dict) -> dict:
    sb = get_supabase()
    lead = sb.table("leads").select("*").eq("id", lead_id).maybe_single().execute()
    if not lead.data:
        raise HTTPException(404, "lead not found")
    l = lead.data
    phone = (l.get("phone") or "").strip()
    if not phone:
        raise HTTPException(400, "lead has no phone number")

    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        digits = "1" + digits
    e164 = "+" + digits

    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message is required")

    s = get_settings()
    import httpx
    url = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"
    r = httpx.post(url,
        auth=(s.twilio_account_sid, s.twilio_auth_token),
        data={"From": s.twilio_from_number, "To": e164, "Body": message},
        timeout=15)

    ok = r.status_code < 300
    log_activity(lead_id, "sms", "sent" if ok else "error",
                 summary=message[:120],
                 agent="manual",
                 payload={"to": e164, "sid": r.json().get("sid") if ok else None,
                          "error": None if ok else r.text[:200]})
    if not ok:
        raise HTTPException(502, f"Twilio error: {r.text[:200]}")
    return {"ok": True, "to": e164, "sid": r.json().get("sid")}


@router.post("/{lead_id}/email")
def send_email(lead_id: str, body: dict) -> dict:
    sb = get_supabase()
    lead = sb.table("leads").select("*").eq("id", lead_id).maybe_single().execute()
    if not lead.data:
        raise HTTPException(404, "lead not found")
    l = lead.data
    email = (l.get("email") or "").strip()
    if not email:
        raise HTTPException(400, "lead has no email address")

    subject = (body.get("subject") or "").strip()
    message = (body.get("message") or "").strip()
    if not subject or not message:
        raise HTTPException(400, "subject and message are required")

    s = get_settings()
    import httpx
    try:
        from ..studio.email_template import build_html
        html = build_html(
            state=l.get("state") or "",
            lead_name=l.get("contact_name") or l.get("business_name") or "there",
        )
        html = html.replace("</body>", f"<div style='padding:20px'>{message}</div></body>")
    except Exception:
        html = f"<p>{message}</p>"

    r = httpx.post("https://api.postmarkapp.com/email",
        headers={"Accept":"application/json","Content-Type":"application/json",
                 "X-Postmark-Server-Token": s.postmark_server_token},
        json={"From": s.postmark_from_email, "To": email,
              "Subject": subject, "HtmlBody": html, "MessageStream": "outbound"},
        timeout=15)

    ok = r.status_code < 300
    log_activity(lead_id, "email", "sent" if ok else "error",
                 summary=f"Subject: {subject}",
                 agent="manual",
                 payload={"to": email, "subject": subject, "error": None if ok else r.text[:200]})
    if not ok:
        raise HTTPException(502, f"Postmark error: {r.text[:200]}")
    return {"ok": True, "to": email}


@router.post("/")
def create_lead(lead: Lead) -> dict:
    if dedupe.is_duplicate(lead.dot_number, lead.mc_number):
        raise HTTPException(409, "duplicate lead")
    data = lead.model_dump(exclude_none=True)
    data["score"] = scoring.score_lead(data)
    if "company_name" in data and "business_name" not in data:
        data["business_name"] = data.pop("company_name")
    if "stage" in data and "status" not in data:
        data["status"] = data.pop("stage")
    if not data.get("business_name"):
        data["business_name"] = (
            data.get("contact_name") or data.get("source_ref") or "Unknown"
        )
    res = get_supabase().table("leads").insert(data).execute()
    return {"ok": True, "lead": (res.data or [None])[0]}


@router.patch("/{lead_id}")
def update_lead(lead_id: str, patch: dict) -> dict:
    if "company_name" in patch and "business_name" not in patch:
        patch["business_name"] = patch.pop("company_name")
    old_status = None
    if "stage" in patch and "status" not in patch:
        patch["status"] = patch.pop("stage")
    if "status" in patch:
        # Log stage change as activity
        sb = get_supabase()
        old = (sb.table("leads").select("status").eq("id", lead_id).maybe_single().execute()).data
        old_status = (old or {}).get("status")
    get_supabase().table("leads").update(patch).eq("id", lead_id).execute()
    if "status" in patch and old_status and old_status != patch["status"]:
        log_activity(lead_id, "stage_change", "sent",
                     summary=f"Stage: {old_status} → {patch['status']}",
                     agent="manual")
    return {"ok": True}

"""Carrier Factoring Management API.

Internal (bearer auth):
  GET    /api/factoring              list all factoring assignments
  POST   /api/factoring              create new assignment + send NOA
  PATCH  /api/factoring/{id}         update assignment
  DELETE /api/factoring/{id}         deactivate assignment
  POST   /api/factoring/{id}/resend  resend NOA signing email
  GET    /api/factoring/stats        summary stats
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from ..logging_service import get_logger
from ..settings import get_settings
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("factoring")

SITE_URL = os.getenv("SITE_URL", "https://www.3lakeslogistics.com")
API_URL  = os.getenv("RENDER_EXTERNAL_URL", "https://three-lakes-logistics-api.onrender.com")

router = APIRouter()


class FactoringCreate(BaseModel):
    carrier_name:         str
    carrier_mc:           str | None = None
    carrier_dot:          str | None = None
    carrier_email:        str | None = None
    carrier_id:           str | None = None
    factor_company:       str
    factor_contact:       str | None = None
    factor_email:         str | None = None
    factor_phone:         str | None = None
    factor_address:       str | None = None
    carrier_acct_at_factor: str | None = None
    payment_method:       str = "ACH"
    remittance_email:     str | None = None
    remittance_notes:     str | None = None
    notes:                str | None = None
    send_noa:             bool = True


class FactoringUpdate(BaseModel):
    factor_company:       str | None = None
    factor_contact:       str | None = None
    factor_email:         str | None = None
    factor_phone:         str | None = None
    factor_address:       str | None = None
    carrier_acct_at_factor: str | None = None
    payment_method:       str | None = None
    remittance_email:     str | None = None
    remittance_notes:     str | None = None
    noa_status:           str | None = None
    active:               bool | None = None
    notes:                str | None = None


@router.get("/stats", dependencies=[Depends(require_bearer)])
def factoring_stats() -> dict:
    sb = get_supabase()
    rows = sb.table("carrier_factoring").select("noa_status,active,factor_company").execute().data or []
    total = len(rows)
    active = sum(1 for r in rows if r.get("active"))
    signed = sum(1 for r in rows if r.get("noa_status") == "signed")
    pending = sum(1 for r in rows if r.get("noa_status") in ("pending", "sent"))
    companies = len(set(r["factor_company"] for r in rows if r.get("factor_company")))
    return {"total": total, "active": active, "signed": signed, "pending": pending, "factor_companies": companies}


@router.get("", dependencies=[Depends(require_bearer)])
def list_factoring(active: bool | None = None, noa_status: str | None = None, limit: int = 200) -> dict:
    sb = get_supabase()
    q = sb.table("carrier_factoring").select("*").order("created_at", desc=True).limit(limit)
    if active is not None:
        q = q.eq("active", active)
    if noa_status:
        q = q.eq("noa_status", noa_status)
    rows = q.execute().data or []
    return {"count": len(rows), "items": rows}


@router.post("", dependencies=[Depends(require_bearer)])
async def create_factoring(body: FactoringCreate) -> dict:
    sb = get_supabase()
    row = sb.table("carrier_factoring").insert({
        "carrier_name":          body.carrier_name,
        "carrier_mc":            body.carrier_mc,
        "carrier_dot":           body.carrier_dot,
        "carrier_email":         body.carrier_email,
        "carrier_id":            body.carrier_id,
        "factor_company":        body.factor_company,
        "factor_contact":        body.factor_contact,
        "factor_email":          body.factor_email,
        "factor_phone":          body.factor_phone,
        "factor_address":        body.factor_address,
        "carrier_acct_at_factor": body.carrier_acct_at_factor,
        "payment_method":        body.payment_method,
        "remittance_email":      body.remittance_email,
        "remittance_notes":      body.remittance_notes,
        "notes":                 body.notes,
        "noa_status":            "pending",
    }).execute().data[0]

    sign_url = None
    if body.send_noa and body.carrier_email:
        # Create a signature request for the NOA
        noa_row = sb.table("signature_requests").insert({
            "agreement_type": "factoring_acknowledgment",
            "carrier_name":   body.carrier_name,
            "carrier_email":  body.carrier_email,
            "carrier_dot":    body.carrier_dot,
            "metadata":       {"factoring_id": str(row["id"]), "factor_company": body.factor_company},
        }).execute().data[0]
        token = noa_row.get("token", "")
        sign_url = f"{SITE_URL}/sign.html?token={token}"
        # update factoring record with token
        sb.table("carrier_factoring").update({"noa_token": token, "noa_status": "sent"}).eq("id", row["id"]).execute()
        await _send_noa_email(body.carrier_email, body.carrier_name, body.factor_company, sign_url)

    return {"ok": True, "id": row["id"], "sign_url": sign_url}


@router.patch("/{fid}", dependencies=[Depends(require_bearer)])
def update_factoring(fid: str, body: FactoringUpdate) -> dict:
    sb = get_supabase()
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(400, "No fields to update")
    sb.table("carrier_factoring").update(data).eq("id", fid).execute()
    return {"ok": True}


@router.delete("/{fid}", dependencies=[Depends(require_bearer)])
def deactivate_factoring(fid: str) -> dict:
    sb = get_supabase()
    sb.table("carrier_factoring").update({"active": False}).eq("id", fid).execute()
    return {"ok": True}


@router.post("/{fid}/resend", dependencies=[Depends(require_bearer)])
async def resend_noa(fid: str) -> dict:
    sb = get_supabase()
    rows = sb.table("carrier_factoring").select("*").eq("id", fid).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Factoring record not found")
    rec = rows[0]
    if not rec.get("carrier_email"):
        raise HTTPException(400, "No carrier email on record")

    # Create a fresh signature request
    noa_row = sb.table("signature_requests").insert({
        "agreement_type": "factoring_acknowledgment",
        "carrier_name":   rec["carrier_name"],
        "carrier_email":  rec["carrier_email"],
        "carrier_dot":    rec.get("carrier_dot"),
        "metadata":       {"factoring_id": fid, "factor_company": rec.get("factor_company", "")},
    }).execute().data[0]
    token = noa_row.get("token", "")
    sign_url = f"{SITE_URL}/sign.html?token={token}"
    sb.table("carrier_factoring").update({"noa_token": token, "noa_status": "sent"}).eq("id", fid).execute()
    await _send_noa_email(rec["carrier_email"], rec["carrier_name"], rec.get("factor_company", ""), sign_url)
    return {"ok": True, "sign_url": sign_url}


async def _send_noa_email(to: str, carrier_name: str, factor_company: str, sign_url: str) -> None:
    s = get_settings()
    if not s.postmark_server_token:
        log.warning("Postmark not configured — NOA email not sent to %s", to)
        return
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
      <div style="background:#1e288b;padding:20px 24px">
        <h1 style="color:#fff;margin:0;font-size:20px">Notice of Assignment — Action Required</h1>
        <p style="color:rgba(255,255,255,.7);margin:6px 0 0;font-size:13px">3 Lakes Logistics LLC</p>
      </div>
      <div style="padding:24px">
        <p>Hi {carrier_name},</p>
        <p>We have received notification that you are factoring your freight receivables with <strong>{factor_company}</strong>.</p>
        <p>Please review and sign the <strong>Factoring Acknowledgment &amp; Notice of Assignment</strong> so we can update our payment records and direct your settlements to {factor_company}.</p>
        <p style="margin:28px 0;text-align:center">
          <a href="{sign_url}" style="background:#ea580c;color:#fff;padding:14px 32px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:15px;display:inline-block">
            Review &amp; Sign Notice of Assignment
          </a>
        </p>
        <p style="font-size:13px;color:#666"><strong>Important:</strong> We cannot redirect your settlement payments to {factor_company} until this document is signed. This link expires in 30 days.</p>
        <p style="font-size:13px;color:#666">Questions? Call us at <a href="tel:6614669932">661-466-9932</a> or email <a href="mailto:loads@3lakeslogistics.com">loads@3lakeslogistics.com</a>.</p>
      </div>
      <div style="background:#f5f5f5;padding:14px 24px;font-size:12px;color:#888;text-align:center">
        &copy; 2026 3 Lakes Logistics LLC &nbsp;|&nbsp; 661-466-9932
      </div>
    </div>
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.postmarkapp.com/email",
                headers={"X-Postmark-Server-Token": s.postmark_server_token, "Content-Type": "application/json"},
                json={
                    "From":          s.postmark_from_email,
                    "To":            to,
                    "Subject":       f"Action Required: Sign Factoring Notice of Assignment — 3 Lakes Logistics",
                    "HtmlBody":      html,
                    "TextBody":      f"Hi {carrier_name},\n\nPlease sign your Factoring NOA with {factor_company}: {sign_url}\n\nThis link expires in 30 days.\n\n3 Lakes Logistics — 661-466-9932",
                    "MessageStream": "outbound",
                    "Tag":           "factoring-noa",
                },
            )
            if resp.status_code != 200:
                log.error("Postmark NOA send failed: %s", resp.text)
    except Exception as exc:
        log.error("Failed to send NOA email: %s", exc)

"""Leads — powers the EAGLE EYE `Leads` page and Vance outbound."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..models.lead import Lead
from ..prospecting import dedupe, scoring
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


# ── Quick Intake ──────────────────────────────────────────────────────────────

def _quick_intake_email_html(name: str, contact: str, onboard_url: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:40px 20px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08);">

  <!-- Header -->
  <tr><td style="background:#001f3f;padding:30px 40px;text-align:center;">
    <div style="font-size:26px;font-weight:900;color:#ffffff;letter-spacing:-0.5px;">3 Lakes Logistics</div>
    <div style="font-size:12px;color:rgba(255,255,255,.55);margin-top:4px;letter-spacing:1.5px;text-transform:uppercase;">Carrier Operations · Detroit, MI</div>
  </td></tr>

  <!-- Body -->
  <tr><td style="padding:36px 40px;">
    <p style="margin:0 0 18px;font-size:22px;font-weight:800;color:#001f3f;">
      Great talking with you{', ' + contact if contact else ''}!
    </p>
    <p style="margin:0 0 20px;font-size:15px;color:#444;line-height:1.7;">
      We'd love to get <strong>{name}</strong> activated in our network. To get you set up and moving loads,
      please click the button below to complete your carrier application — it takes about 5 minutes.
    </p>

    <!-- CTA -->
    <div style="text-align:center;margin:32px 0;">
      <a href="{onboard_url}" style="background:#001f3f;color:#ffffff;text-decoration:none;font-size:15px;font-weight:700;padding:16px 40px;border-radius:8px;display:inline-block;letter-spacing:.3px;">
        Complete My Carrier Application →
      </a>
    </div>

    <!-- What you'll need -->
    <div style="background:#f8fafc;border-left:4px solid #e8a020;border-radius:0 8px 8px 0;padding:18px 20px;margin:24px 0;">
      <div style="font-weight:800;font-size:13px;color:#001f3f;margin-bottom:10px;text-transform:uppercase;letter-spacing:.5px;">What you'll need</div>
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="width:50%;vertical-align:top;padding-right:10px;">
            <ul style="margin:0;padding:0 0 0 18px;font-size:13px;color:#555;line-height:2;">
              <li>MC/DOT authority number</li>
              <li>Certificate of Insurance (COI)</li>
              <li>W-9 (EIN or SSN)</li>
            </ul>
          </td>
          <td style="width:50%;vertical-align:top;">
            <ul style="margin:0;padding:0 0 0 18px;font-size:13px;color:#555;line-height:2;">
              <li>Voided check (direct deposit)</li>
              <li>CDL copy (owner-operators)</li>
              <li>Equipment details</li>
            </ul>
          </td>
        </tr>
      </table>
    </div>

    <!-- What we offer -->
    <p style="margin:20px 0 8px;font-size:14px;font-weight:700;color:#001f3f;">What you get with 3 Lakes</p>
    <ul style="margin:0 0 24px;padding:0 0 0 18px;font-size:13px;color:#555;line-height:2.1;">
      <li>Consistent freight — Michigan, Ohio, Tennessee, Southeast lanes</li>
      <li>Net-7 quick pay (keep 92% of the load rate)</li>
      <li>Dedicated dispatcher — one call, no middlemen</li>
      <li>Fuel advances available after first load</li>
    </ul>

    <p style="margin:0;font-size:13px;color:#888;">
      Questions? Reply to this email or call us at <strong>(313) 555-0100</strong>.<br>
      We're here Mon–Fri 6am–8pm EST.
    </p>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#f8fafc;padding:20px 40px;border-top:1px solid #e8ecf0;text-align:center;">
    <p style="margin:0;font-size:11px;color:#aaa;line-height:1.7;">
      3 Lakes Logistics · Detroit, MI · dispatch@3lakeslogistics.com<br>
      You received this because our team spoke with you about joining our carrier network.
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


async def _send_carrier_invitation(
    email: str,
    business_name: str,
    contact_name: str | None,
    lead_id: str,
) -> bool:
    s = get_settings()
    if not s.postmark_server_token:
        return False
    onboard_url = f"https://3lakeslogistics.com/carrier-onboarding?lead={lead_id}"
    contact = contact_name or ""
    html = _quick_intake_email_html(business_name, contact, onboard_url)
    subject = f"{business_name} — Complete Your Carrier Application"
    text = (
        f"Hi {contact or business_name},\n\n"
        f"Great speaking with you! Please complete your carrier application at:\n{onboard_url}\n\n"
        "You'll need: MC/DOT authority, COI, W-9, voided check, CDL copy.\n\n"
        "Questions? dispatch@3lakeslogistics.com\n\n— 3 Lakes Logistics"
    )
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(
                "https://api.postmarkapp.com/email",
                headers={
                    "X-Postmark-Server-Token": s.postmark_server_token,
                    "Content-Type": "application/json",
                },
                json={
                    "From": s.postmark_from_email,
                    "To": email,
                    "Subject": subject,
                    "HtmlBody": html,
                    "TextBody": text,
                    "MessageStream": "outbound",
                    "Tag": "carrier-invitation",
                },
            )
        return r.status_code == 200
    except Exception:
        return False


@router.post("/{lead_id}/quick-intake")
async def quick_intake(
    lead_id: str,
    data: dict,
    bg: BackgroundTasks,
) -> dict:
    """Capture key fields from a carrier call and optionally trigger onboarding email.

    Accepted fields (all optional):
        email, contact_name, dot_number, mc_number,
        equipment_type, fleet_size, state, notes, status
    """
    sb = get_supabase()

    # Load existing lead
    row = sb.table("leads").select("*").eq("id", lead_id).single().execute()
    if not row.data:
        raise HTTPException(404, "Lead not found")
    lead = row.data

    # Build patch — only update fields that were actually sent
    allowed = {"email", "contact_name", "dot_number", "mc_number",
               "equipment_type", "fleet_size", "state", "notes", "status"}
    patch = {k: v for k, v in data.items() if k in allowed and v not in (None, "")}

    if not patch.get("status"):
        # Auto-advance status
        current = (lead.get("status") or "").lower()
        if current in ("new lead", "new", ""):
            patch["status"] = "contacted"

    if patch:
        sb.table("leads").update(patch).eq("id", lead_id).execute()

    # Send invitation email if email is now known
    email = patch.get("email") or lead.get("email")
    email_sent = False
    if email:
        biz  = lead.get("business_name") or lead.get("company_name") or "Your Company"
        name = patch.get("contact_name") or lead.get("contact_name")
        bg.add_task(_send_carrier_invitation, email, biz, name, lead_id)
        email_sent = True

    return {
        "ok": True,
        "lead_id": lead_id,
        "fields_saved": list(patch.keys()),
        "email_sent": email_sent,
        "email_to": email if email_sent else None,
    }


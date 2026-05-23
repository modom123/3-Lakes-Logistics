"""Broker intake, onboarding email, and self-service registration.

Endpoints:
  POST /api/brokers/intake        — register a broker (form or API)
  GET  /api/brokers               — list all brokers
  GET  /api/brokers/{id}          — single broker record
  POST /api/brokers/{id}/resend   — resend onboarding email manually
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from ..api.deps import require_bearer
from ..settings import get_settings
from ..supabase_client import get_supabase

log = logging.getLogger("3ll.brokers")
router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────────────────

class BrokerIntake(BaseModel):
    broker_name: str
    broker_mc: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    dot_number: str | None = None
    payment_terms: str = "Net-30"
    factoring_allowed: bool = True
    notes: str | None = None
    source: str = "intake_form"


# ── Email templates ───────────────────────────────────────────────────────────

_CONTACT_BLOCK = """
<div style="border-top:2px solid #C8902A;padding:20px;margin-top:30px;text-align:center;">
  <p style="color:#0B2545;font-size:14px;margin:0 0 10px;"><strong>Questions? We're Here.</strong></p>
  <p style="color:#334155;font-size:13px;margin:0;line-height:2;">
    <strong>📞 Dispatch:</strong> (555) 000-1234<br>
    <strong>✉️ Email:</strong> <a href="mailto:dispatch@3lakeslogistics.com" style="color:#C8902A;text-decoration:none;">dispatch@3lakeslogistics.com</a>
  </p>
</div>"""


def _build_welcome_html(broker_name: str, contact_name: str | None, broker_id: str, broker_mc: str | None) -> str:
    greeting = contact_name or broker_name
    mc_line = f"<p style='color:#64748b;font-size:12px;margin-top:4px;'>MC# {broker_mc}</p>" if broker_mc else ""
    return f"""<html><body style="font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;max-width:650px;margin:0 auto;background:#f5f5f5;">
<div style="background:#0B2545;padding:28px 20px;text-align:center;border-bottom:4px solid #C8902A;">
  <h1 style="color:#C8902A;margin:0;font-size:26px;font-weight:700;">3 Lakes Logistics</h1>
  <p style="color:#93C5FD;margin:8px 0 0;font-size:13px;letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">Broker Partnership Portal</p>
</div>
<div style="background:#fff;padding:28px 30px;margin:20px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">

  <h2 style="color:#0B2545;margin-top:0;">Welcome, {greeting}!</h2>
  {mc_line}
  <p style="color:#555;font-size:15px;line-height:1.7;">
    You're now registered as a broker partner with <strong>3 Lakes Logistics</strong>.
    This email covers everything you need to know to start booking loads with our fleet.
  </p>

  <!-- How to Submit Loads -->
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
    <h3 style="color:#0B2545;margin-top:0;">📋 How to Submit Loads</h3>
    <div style="color:#334155;font-size:14px;line-height:1.9;">
      <p><strong>Option 1 — Email Rate Con:</strong> Send your rate confirmation to
        <a href="mailto:loads@3lakeslogistics.com" style="color:#C8902A;">loads@3lakeslogistics.com</a>.
        Our AI system parses it instantly and dispatches a driver.</p>
      <p><strong>Option 2 — Direct Portal:</strong> Log into your carrier partner portal to post loads, track status, and download PODs.</p>
      <p><strong>Option 3 — EDI / API:</strong> Contact us to configure a direct EDI 204 feed or REST API integration.</p>
      <p style="color:#64748b;font-size:13px;"><strong>Accepted formats:</strong> PDF, image (JPG/PNG), or plain-text rate confirmation. BOL and POD required at delivery.</p>
    </div>
  </div>

  <!-- Document Requirements -->
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
    <h3 style="color:#0B2545;margin-top:0;">📄 Required Documents per Load</h3>
    <div style="color:#334155;font-size:14px;line-height:2;">
      <p>✅ <strong>Rate Confirmation</strong> — signed before dispatch</p>
      <p>✅ <strong>Bill of Lading (BOL)</strong> — at pickup</p>
      <p>✅ <strong>Proof of Delivery (POD)</strong> — at delivery (triggers payment)</p>
      <p>⚡ <strong>Lumper receipts, detention forms</strong> — within 24 hrs of delivery</p>
    </div>
    <p style="color:#64748b;font-size:12px;margin-top:8px;">Missing docs delay payment. POD is the payment trigger — no POD = no payment cycle.</p>
  </div>

  <!-- Payment Terms -->
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
    <h3 style="color:#0B2545;margin-top:0;">💳 Payment Policy</h3>
    <div style="color:#334155;font-size:14px;line-height:1.9;">
      <p><strong>Standard terms:</strong> Net-30 from confirmed POD date</p>
      <p><strong>Quick-pay:</strong> Available at a 2% discount for payment within 5 business days</p>
      <p><strong>Factoring:</strong> We accept factoring — include your NOA with your first rate con</p>
      <p><strong>Disputes:</strong> Must be raised within 7 days of invoice date. Email
        <a href="mailto:billing@3lakeslogistics.com" style="color:#C8902A;">billing@3lakeslogistics.com</a>
        with load number and reason.</p>
      <p><strong>Double-brokering:</strong> Strictly prohibited. Violations result in immediate blacklist.</p>
    </div>
  </div>

  <!-- What We Cover -->
  <div style="background:#EFF6FF;border-left:4px solid #3B82F6;padding:18px 20px;margin:20px 0;border-radius:4px;">
    <h3 style="color:#1E40AF;margin-top:0;">🚚 Our Fleet Capabilities</h3>
    <div style="color:#334155;font-size:14px;line-height:2;">
      <p>✅ Dry van, reefer, flatbed, and step-deck</p>
      <p>✅ OTR and regional lanes — 48 contiguous states</p>
      <p>✅ Team drivers available for time-sensitive freight</p>
      <p>✅ Hazmat-certified drivers on request</p>
      <p>✅ Real-time GPS tracking shared on every active load</p>
      <p>✅ AI-dispatched — our system monitors pickup windows, ETA, and delays 24/7</p>
    </div>
  </div>

  <!-- Compliance -->
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
    <h3 style="color:#0B2545;margin-top:0;">🛡️ Compliance & Insurance</h3>
    <div style="color:#334155;font-size:14px;line-height:1.9;">
      <p><strong>USDOT / MC:</strong> Verified active with FMCSA</p>
      <p><strong>Cargo insurance:</strong> $100,000 minimum per load (certificate available on request)</p>
      <p><strong>Auto liability:</strong> $1,000,000 CSL</p>
      <p><strong>CSA score:</strong> Monitored monthly — we maintain clean safety records</p>
    </div>
  </div>

  <!-- Next Steps -->
  <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:20px;margin:20px 0;">
    <h3 style="color:#16a34a;margin-top:0;">🎯 You're Ready to Book</h3>
    <div style="color:#334155;font-size:14px;line-height:1.9;">
      <p><strong>Step 1</strong> — Email your first rate con to <a href="mailto:loads@3lakeslogistics.com" style="color:#C8902A;">loads@3lakeslogistics.com</a></p>
      <p><strong>Step 2</strong> — Our AI dispatches a driver and sends you a confirmation within 30 minutes</p>
      <p><strong>Step 3</strong> — Track your load in real time — tracking link sent at pickup</p>
      <p><strong>Step 4</strong> — POD confirmed → payment processed on your terms</p>
    </div>
  </div>

  {_CONTACT_BLOCK}
  <p style="color:#94a3b8;font-size:11px;margin-top:24px;text-align:center;">Broker ID: {broker_id}</p>
</div>
</body></html>"""


def _build_welcome_text(broker_name: str, contact_name: str | None, broker_id: str) -> str:
    greeting = contact_name or broker_name
    return f"""Welcome, {greeting}!

You're registered as a broker partner with 3 Lakes Logistics.

HOW TO SUBMIT LOADS
- Email rate con to loads@3lakeslogistics.com
- Our AI parses it and dispatches a driver within 30 minutes

REQUIRED DOCS PER LOAD
- Rate Confirmation (before dispatch)
- Bill of Lading (at pickup)
- Proof of Delivery (triggers payment)

PAYMENT TERMS
- Net-30 from confirmed POD
- Quick-pay available (2% discount, paid in 5 days)
- Factoring accepted — include NOA with first rate con

COMPLIANCE
- FMCSA active | $100K cargo insurance | $1M auto liability

Questions? dispatch@3lakeslogistics.com | (555) 000-1234

Broker ID: {broker_id}
"""


# ── Email sender ──────────────────────────────────────────────────────────────

async def send_broker_welcome(
    broker_id: str,
    broker_name: str,
    broker_mc: str | None,
    contact_name: str | None,
    email: str,
    trigger: str = "intake",
) -> bool:
    s = get_settings()
    if not s.postmark_server_token:
        log.warning("Postmark not configured — broker welcome email skipped for %s", email)
        return False

    subject = f"Welcome to 3 Lakes Logistics — Broker Onboarding Guide ({broker_name})"
    html = _build_welcome_html(broker_name, contact_name, broker_id, broker_mc)
    text = _build_welcome_text(broker_name, contact_name, broker_id)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
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
                    "Tag": "broker-welcome",
                },
            )
        sent = resp.status_code == 200
    except Exception as exc:
        log.error("broker welcome email failed for %s: %s", email, exc)
        sent = False

    # Audit log regardless
    try:
        get_supabase().table("broker_welcome_emails").insert({
            "broker_id": broker_id,
            "broker_mc": broker_mc,
            "email": email,
            "subject": subject,
            "trigger": trigger,
        }).execute()
    except Exception:
        pass

    if sent:
        get_supabase().table("brokers").update({
            "onboarding_sent": True,
            "welcome_sent_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", broker_id).execute()
        log.info("broker welcome sent broker_id=%s email=%s trigger=%s", broker_id, email, trigger)

    return sent


def _upsert_broker(
    broker_name: str,
    broker_mc: str | None,
    contact_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    dot_number: str | None = None,
    payment_terms: str = "Net-30",
    factoring_allowed: bool = True,
    notes: str | None = None,
    source: str = "manual",
) -> dict:
    """Insert or update broker record. Returns the broker row."""
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    if broker_mc:
        existing = sb.table("brokers").select("*").eq("broker_mc", broker_mc).limit(1).execute().data
        if existing:
            update: dict = {"updated_at": now, "source": source}
            for field, val in [("broker_name", broker_name), ("contact_name", contact_name),
                               ("email", email), ("phone", phone)]:
                if val:
                    update[field] = val
            sb.table("brokers").update(update).eq("broker_mc", broker_mc).execute()
            return sb.table("brokers").select("*").eq("broker_mc", broker_mc).single().execute().data

    row = {
        "broker_name": broker_name,
        "broker_mc": broker_mc,
        "contact_name": contact_name,
        "email": email,
        "phone": phone,
        "address": address,
        "dot_number": dot_number,
        "payment_terms": payment_terms,
        "factoring_allowed": factoring_allowed,
        "notes": notes,
        "source": source,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }
    result = sb.table("brokers").insert(row).execute()
    return result.data[0]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/intake", status_code=201)
async def broker_intake(body: BrokerIntake, bg: BackgroundTasks) -> dict:
    """Register a broker and send welcome + onboarding email."""
    broker = _upsert_broker(
        broker_name=body.broker_name,
        broker_mc=body.broker_mc,
        contact_name=body.contact_name,
        email=body.email,
        phone=body.phone,
        address=body.address,
        dot_number=body.dot_number,
        payment_terms=body.payment_terms,
        factoring_allowed=body.factoring_allowed,
        notes=body.notes,
        source=body.source,
    )
    broker_id = broker["id"]

    email_queued = False
    if body.email:
        bg.add_task(
            send_broker_welcome,
            broker_id, body.broker_name, body.broker_mc,
            body.contact_name, body.email, "intake",
        )
        email_queued = True

    log.info("broker intake broker_id=%s mc=%s email_queued=%s", broker_id, body.broker_mc, email_queued)
    return {
        "ok": True,
        "broker_id": broker_id,
        "broker_name": broker["broker_name"],
        "broker_mc": broker.get("broker_mc"),
        "email_queued": email_queued,
        "message": "Broker registered. Onboarding email queued." if email_queued else "Broker registered (no email on file).",
    }


@router.get("/", dependencies=[Depends(require_bearer)])
def list_brokers(
    status: str | None = None,
    limit: int = 100,
) -> list:
    sb = get_supabase()
    q = sb.table("brokers").select("*")
    if status:
        q = q.eq("status", status)
    return q.order("created_at", desc=True).limit(min(limit, 500)).execute().data


@router.get("/{broker_id}", dependencies=[Depends(require_bearer)])
def get_broker(broker_id: str) -> dict:
    sb = get_supabase()
    res = sb.table("brokers").select("*").eq("id", broker_id).single().execute()
    if not res.data:
        raise HTTPException(404, "Broker not found")
    sends = sb.table("broker_welcome_emails").select("email,trigger,sent_at") \
               .eq("broker_id", broker_id).order("sent_at", desc=True).limit(5).execute()
    return {**res.data, "email_history": sends.data or []}


@router.post("/{broker_id}/resend", dependencies=[Depends(require_bearer)])
async def resend_onboarding(broker_id: str, bg: BackgroundTasks) -> dict:
    """Manually resend onboarding email to a broker."""
    sb = get_supabase()
    res = sb.table("brokers").select("*").eq("id", broker_id).single().execute()
    if not res.data:
        raise HTTPException(404, "Broker not found")
    broker = res.data
    if not broker.get("email"):
        raise HTTPException(400, "No email address on file for this broker")
    bg.add_task(
        send_broker_welcome,
        broker_id, broker["broker_name"], broker.get("broker_mc"),
        broker.get("contact_name"), broker["email"], "manual",
    )
    return {"ok": True, "broker_id": broker_id, "email": broker["email"], "message": "Onboarding email re-queued."}

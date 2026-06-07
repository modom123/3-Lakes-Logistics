"""Agreement e-sign API.

Internal (bearer auth):
  GET  /api/agreements/requests         list all signature requests
  POST /api/agreements/send             create request + email signing link
  DELETE /api/agreements/requests/{id}  cancel a pending request

Public (token auth):
  GET  /api/agreements/sign/{token}     fetch request details for signing page
  POST /api/agreements/sign/{token}     submit signature
"""
from __future__ import annotations

import os
import random
import string
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..logging_service import get_logger
from ..settings import get_settings
from ..supabase_client import get_supabase
from .deps import require_bearer
from fastapi import Depends

log = get_logger("agreements")

AGREEMENT_LABELS = {
    "carrier_agreement":         "Carrier Dispatch Agreement",
    "broker_agreement":          "Broker–Carrier Agreement",
    "terms_of_service":          "Terms of Service",
    "independent_contractor":    "Independent Contractor Agreement",
    "nda":                       "Non-Disclosure Agreement",
    "non_solicitation":          "Non-Solicitation Agreement",
    "driver_lease_on":           "Driver Lease-On Agreement",
    "fuel_advance":              "Fuel Advance Agreement",
    "cargo_claims":              "Cargo Claims Procedure",
    "rate_confirmation":         "Rate Confirmation",
    "insurance_requirements":    "Insurance Minimum Requirements",
    "dispatcher_service":        "Dispatcher Service Agreement",
    "factoring_acknowledgment":  "Factoring Acknowledgment & Notice of Assignment",
}

AGREEMENT_PATHS = {
    "carrier_agreement":         "/carrier-agreement.html",
    "broker_agreement":          "/broker-agreement.html",
    "terms_of_service":          "/terms-of-service.html",
    "independent_contractor":    "/independent-contractor-agreement.html",
    "nda":                       "/nda.html",
    "non_solicitation":          "/non-solicitation-agreement.html",
    "driver_lease_on":           "/driver-lease-on-agreement.html",
    "fuel_advance":              "/fuel-advance-agreement.html",
    "cargo_claims":              "/cargo-claims-procedure.html",
    "rate_confirmation":         "/rate-confirmation-template.html",
    "insurance_requirements":    "/insurance-requirements.html",
    "dispatcher_service":        "/dispatcher-service-agreement.html",
    "factoring_acknowledgment":  "/factoring-acknowledgment.html",
}

SITE_URL = os.getenv("SITE_URL", "https://www.3lakeslogistics.com")
API_URL  = os.getenv("RENDER_EXTERNAL_URL", "https://three-lakes-logistics-api.onrender.com")

router = APIRouter()


# ── Internal endpoints ────────────────────────────────────────────────────────

def _generate_agreement_no() -> str:
    digits = "".join(random.choices(string.digits, k=6))
    return f"3LL-DSP-{digits}"


class SendRequest(BaseModel):
    agreement_type: str
    carrier_name: str
    carrier_email: str
    carrier_dot: str | None = None
    carrier_mc: str | None = None
    carrier_phone: str | None = None
    service_plan: str | None = None
    agreement_no: str | None = None
    metadata: dict | None = None


@router.get("/requests", dependencies=[Depends(require_bearer)])
def list_requests(status: str | None = None, limit: int = 200) -> dict:
    sb = get_supabase()
    q = (
        sb.table("signature_requests")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        q = q.eq("status", status)
    rows = q.execute().data or []
    return {"count": len(rows), "items": rows}


@router.post("/send", dependencies=[Depends(require_bearer)])
async def send_for_signature(body: SendRequest) -> dict:
    if body.agreement_type not in AGREEMENT_LABELS:
        raise HTTPException(400, f"agreement_type must be one of {list(AGREEMENT_LABELS)}")

    agreement_no = body.agreement_no or _generate_agreement_no()

    meta = body.metadata or {}
    if body.carrier_mc:
        meta["carrier_mc"] = body.carrier_mc
    if body.carrier_phone:
        meta["carrier_phone"] = body.carrier_phone
    if body.service_plan:
        meta["service_plan"] = body.service_plan
    meta["agreement_no"] = agreement_no

    sb = get_supabase()
    result = (
        sb.table("signature_requests")
        .insert({
            "agreement_type": body.agreement_type,
            "carrier_name":   body.carrier_name,
            "carrier_email":  body.carrier_email,
            "carrier_dot":    body.carrier_dot,
            "metadata":       meta,
        })
        .execute()
    )
    row = result.data[0] if result.data else {}
    token = row.get("token", "")
    req_id = row.get("id", "")

    sign_url = f"{SITE_URL}/sign.html?token={token}"
    label    = AGREEMENT_LABELS[body.agreement_type]

    await _send_signing_email(
        body.carrier_email, body.carrier_name, label, sign_url,
        agreement_no=agreement_no,
        carrier_mc=body.carrier_mc,
        service_plan=body.service_plan,
    )

    return {
        "ok": True,
        "id": req_id,
        "token": token,
        "sign_url": sign_url,
        "agreement_no": agreement_no,
    }


@router.delete("/requests/{req_id}", dependencies=[Depends(require_bearer)])
def cancel_request(req_id: str) -> dict:
    sb = get_supabase()
    sb.table("signature_requests").update({"status": "cancelled"}).eq("id", req_id).eq("status", "pending").execute()
    return {"ok": True}


@router.post("/requests/{req_id}/resend", dependencies=[Depends(require_bearer)])
async def resend_signing_email(req_id: str) -> dict:
    sb = get_supabase()
    rows = (
        sb.table("signature_requests")
        .select("*")
        .eq("id", req_id)
        .limit(1)
        .execute()
        .data or []
    )
    if not rows:
        raise HTTPException(404, "Request not found")
    row = rows[0]
    if row["status"] != "pending":
        raise HTTPException(409, f"Cannot resend a {row['status']} request")

    meta = row.get("metadata") or {}
    token = row.get("token", "")
    sign_url = f"{SITE_URL}/sign.html?token={token}"
    label = AGREEMENT_LABELS.get(row["agreement_type"], row["agreement_type"])

    await _send_signing_email(
        row["carrier_email"],
        row["carrier_name"],
        label,
        sign_url,
        agreement_no=meta.get("agreement_no"),
        carrier_mc=meta.get("carrier_mc"),
        service_plan=meta.get("service_plan"),
    )
    log.info("Resent signing email for request %s to %s", req_id, row["carrier_email"])
    return {"ok": True}


# ── Public signing endpoints ──────────────────────────────────────────────────

@router.get("/sign/{token}")
def get_sign_request(token: str) -> dict:
    row = _fetch_token(token)
    return {
        "ok":             True,
        "id":             row["id"],
        "agreement_type": row["agreement_type"],
        "agreement_label": AGREEMENT_LABELS.get(row["agreement_type"], row["agreement_type"]),
        "agreement_path": AGREEMENT_PATHS.get(row["agreement_type"], "/terms-of-service.html"),
        "carrier_name":   row["carrier_name"],
        "status":         row["status"],
        "expires_at":     row["expires_at"],
    }


class SignBody(BaseModel):
    signatory_name: str


@router.post("/sign/{token}")
async def submit_signature(token: str, body: SignBody, request: Request) -> dict:
    if not body.signatory_name.strip():
        raise HTTPException(400, "signatory_name is required")

    row = _fetch_token(token)

    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    # Record in signatures_audit
    sb.table("signatures_audit").insert({
        "carrier_id": None,
        "doc_type":   row["agreement_type"],
        "esign_name": body.signatory_name.strip(),
        "ip":         ip,
        "user_agent": request.headers.get("user-agent", ""),
    }).execute()

    # Create document_vault record
    label = AGREEMENT_LABELS.get(row["agreement_type"], row["agreement_type"])
    vault_row = {
        "doc_type":     "agreement",
        "filename":     f"{label} — {row['carrier_name']}.html",
        "storage_path": f"agreements/signed/{row['id']}",
        "mime_type":    "text/html",
        "scan_status":  "complete",
        "notes":        f"Signed by {body.signatory_name.strip()} on {now[:10]}",
        "bucket":       "documents",
    }
    vault_result = sb.table("document_vault").insert(vault_row).execute()
    doc_id = (vault_result.data or [{}])[0].get("id")

    # Mark request signed
    sb.table("signature_requests").update({
        "status":         "signed",
        "signed_at":      now,
        "signatory_name": body.signatory_name.strip(),
        "signatory_ip":   ip,
        "document_id":    doc_id,
    }).eq("id", row["id"]).execute()

    return {
        "ok":      True,
        "message": f"Agreement signed successfully. A copy has been saved to the document vault.",
        "signed_at": now,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_token(token: str) -> dict:
    sb = get_supabase()
    rows = (
        sb.table("signature_requests")
        .select("*")
        .eq("token", token)
        .limit(1)
        .execute()
        .data or []
    )
    if not rows:
        raise HTTPException(404, "Signing link not found")
    row = rows[0]
    if row["status"] == "signed":
        raise HTTPException(409, "This agreement has already been signed")
    if row["status"] == "cancelled":
        raise HTTPException(410, "This signing link has been cancelled")
    expires = row.get("expires_at", "")
    if expires and datetime.fromisoformat(expires.replace("Z", "+00:00")) < datetime.now(timezone.utc):
        raise HTTPException(410, "This signing link has expired")
    return row


async def _send_signing_email(
    to: str,
    name: str,
    label: str,
    sign_url: str,
    agreement_no: str | None = None,
    carrier_mc: str | None = None,
    service_plan: str | None = None,
) -> None:
    s = get_settings()
    if not s.postmark_server_token:
        log.warning("Postmark not configured — signing email not sent to %s", to)
        return

    detail_rows = ""
    if agreement_no:
        detail_rows += f'<tr><td style="color:#666;padding:4px 0">Agreement #</td><td style="font-weight:bold;padding:4px 0">{agreement_no}</td></tr>'
    if carrier_mc:
        detail_rows += f'<tr><td style="color:#666;padding:4px 0">MC #</td><td style="padding:4px 0">{carrier_mc}</td></tr>'
    if service_plan:
        detail_rows += f'<tr><td style="color:#666;padding:4px 0">Service Plan</td><td style="padding:4px 0">{service_plan}</td></tr>'
    details_block = ""
    if detail_rows:
        details_block = f'<table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:14px">{detail_rows}</table>'

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
      <div style="background:#1e288b;padding:20px 24px">
        <img src="{SITE_URL}/logo.png" alt="3 Lakes Logistics" height="36" style="height:36px" onerror="this.style.display='none'">
        <h1 style="color:#fff;margin:8px 0 0;font-size:20px">Document Ready for Your Signature</h1>
      </div>
      <div style="padding:24px">
        <p>Hi {name},</p>
        <p>Please review and sign your <strong>{label}</strong> with 3 Lakes Logistics.</p>
        {details_block}
        <p style="margin:28px 0;text-align:center">
          <a href="{sign_url}" style="background:#ea580c;color:#fff;padding:14px 32px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:15px;display:inline-block">
            Review &amp; Sign Agreement
          </a>
        </p>
        <p style="font-size:13px;color:#666">This link expires in 30 days. If you did not expect this email, please contact us at <a href="mailto:info@3lakeslogistics.com">info@3lakeslogistics.com</a>.</p>
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
                    "Subject":       f"Please sign: {label} — 3 Lakes Logistics",
                    "HtmlBody":      html,
                    "TextBody":      f"Hi {name},\n\nPlease sign your {label}: {sign_url}\n\nAgreement #: {agreement_no or 'N/A'}\nThis link expires in 30 days.\n\n3 Lakes Logistics",
                    "MessageStream": "outbound",
                    "Tag":           "esign",
                },
            )
            if resp.status_code != 200:
                log.error("Postmark esign send failed: %s", resp.text)
    except Exception as exc:
        log.error("Failed to send signing email: %s", exc)

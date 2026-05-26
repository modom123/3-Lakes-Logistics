"""Rate Confirmation API — send professional rate confirmation emails to carriers."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from ..logging_service import get_logger
from ..settings import get_settings
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("3ll.api.rate_confirmation")
router = APIRouter(dependencies=[Depends(require_bearer)])


class RateConRequest(BaseModel):
    load_id: str
    to_email: str
    cc: list[str] | None = None


def _build_html(load: dict, to_email: str) -> str:
    origin = ", ".join(filter(None, [load.get("origin_city") or load.get("origin"), load.get("origin_state")]))
    dest = ", ".join(filter(None, [load.get("dest_city") or load.get("destination"), load.get("dest_state")]))
    rate = load.get("rate_total") or load.get("rate") or 0
    pickup_raw = load.get("pickup_at") or load.get("pickup_date") or ""
    try:
        pickup = datetime.fromisoformat(str(pickup_raw).replace("Z", "+00:00")).strftime("%B %d, %Y") if pickup_raw else "—"
    except Exception:
        pickup = str(pickup_raw) or "—"

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
  body{{font-family:Arial,sans-serif;color:#1a1a2e;max-width:680px;margin:0 auto;padding:0}}
  .header{{background:#1a1a2e;color:#fff;padding:24px 32px}}
  .header h1{{margin:0;font-size:22px;letter-spacing:0.5px}}
  .header p{{margin:4px 0 0;font-size:12px;color:#a0aec0}}
  .body{{padding:32px}}
  .section{{margin-bottom:24px}}
  .section h3{{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#718096;margin:0 0 8px}}
  .grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
  .field{{background:#f7fafc;border:1px solid #e2e8f0;border-radius:6px;padding:12px}}
  .field label{{font-size:11px;color:#718096;display:block;margin-bottom:2px}}
  .field span{{font-size:15px;font-weight:700;color:#1a1a2e}}
  .rate-box{{background:#1a1a2e;color:#fff;border-radius:8px;padding:20px;text-align:center;margin:16px 0}}
  .rate-box .label{{font-size:12px;color:#a0aec0;margin-bottom:4px}}
  .rate-box .amount{{font-size:32px;font-weight:900;color:#f6c90e}}
  .footer{{background:#f7fafc;border-top:1px solid #e2e8f0;padding:16px 32px;font-size:12px;color:#718096}}
  .badge{{display:inline-block;background:#22c55e;color:#fff;font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px}}
</style></head>
<body>
<div class="header">
  <h1>3 Lakes Logistics</h1>
  <p>Rate Confirmation — {load.get("load_number") or "—"}</p>
</div>
<div class="body">
  <p style="margin-top:0">Dear Carrier,</p>
  <p>Please review the rate confirmation details below for your upcoming load.</p>

  <div class="rate-box">
    <div class="label">TOTAL RATE</div>
    <div class="amount">${float(rate):,.2f}</div>
  </div>

  <div class="section">
    <h3>Load Details</h3>
    <div class="grid">
      <div class="field"><label>Load Number</label><span>{load.get("load_number") or "—"}</span></div>
      <div class="field"><label>Equipment</label><span>{load.get("equipment_type") or load.get("trailer_type") or "—"}</span></div>
      <div class="field"><label>Origin</label><span>{origin or "—"}</span></div>
      <div class="field"><label>Destination</label><span>{dest or "—"}</span></div>
      <div class="field"><label>Pickup Date</label><span>{pickup}</span></div>
      <div class="field"><label>Miles</label><span>{load.get("miles") or "—"}</span></div>
      <div class="field"><label>Commodity</label><span>{load.get("commodity") or "General Freight"}</span></div>
      <div class="field"><label>Weight</label><span>{load.get("weight") or "—"}</span></div>
    </div>
  </div>

  <div class="section">
    <h3>Driver / Carrier</h3>
    <div class="grid">
      <div class="field"><label>Driver</label><span>{load.get("driver_name") or "—"}</span></div>
      <div class="field"><label>Carrier</label><span>{load.get("carrier_name") or "—"}</span></div>
    </div>
  </div>

  <p style="font-size:13px;color:#718096;margin-top:24px">
    By accepting this load, you agree to the terms outlined in your carrier agreement with 3 Lakes Logistics.
    Please contact us immediately if there are any questions or concerns.
  </p>
</div>
<div class="footer">
  3 Lakes Logistics &bull; Mark Odom, Dispatcher &bull; mark@3lakeslogistics.com
  &bull; (313) 555-0100
</div>
</body></html>
"""


@router.post("/rate-confirmation/send")
def send_rate_confirmation(body: RateConRequest) -> dict:
    sb = get_supabase()
    result = sb.table("loads").select("*").eq("id", body.load_id).maybe_single().execute()
    if not result.data:
        raise HTTPException(404, f"Load {body.load_id} not found")
    load = result.data

    html = _build_html(load, body.to_email)
    subject = f"Rate Confirmation — Load #{load.get('load_number') or body.load_id[:8]}"

    s = get_settings()

    # Try Postmark first
    if s.postmark_server_token:
        try:
            from postmarker.core import PostmarkClient  # type: ignore
            client = PostmarkClient(server_token=s.postmark_server_token)
            client.emails.send(
                From=s.postmark_from_email,
                To=body.to_email,
                Cc=", ".join(body.cc) if body.cc else None,
                Subject=subject,
                HtmlBody=html,
                TextBody=f"Rate Confirmation — Load #{load.get('load_number')} — ${float(load.get('rate_total') or load.get('rate') or 0):,.2f}",
                MessageStream="outbound",
            )
            log.info("Rate con sent via Postmark to %s for load %s", body.to_email, body.load_id)
            return {"ok": True, "method": "postmark", "to": body.to_email}
        except Exception as exc:
            log.warning("Postmark rate con failed, falling back to SMTP: %s", exc)

    # Fallback: Hostinger SMTP via loads@ mailbox
    try:
        from ..email.smtp_sender import send_from_mailbox
        send_from_mailbox(
            mailbox="loads",
            to=[body.to_email],
            subject=subject,
            body_html=html,
            body_text=f"Rate Confirmation — {subject}",
            cc=body.cc,
        )
        log.info("Rate con sent via SMTP to %s for load %s", body.to_email, body.load_id)
        return {"ok": True, "method": "smtp", "to": body.to_email}
    except Exception as exc:
        log.error("Rate con SMTP also failed: %s", exc)
        raise HTTPException(502, f"Failed to send rate confirmation: {exc}")

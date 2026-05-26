"""Rate Confirmation — generate and email rate cons to carriers."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..logging_service import get_logger
from ..settings import get_settings
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("route.rate_con")
router = APIRouter(dependencies=[Depends(require_bearer)])

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _build_rate_con_html(load: dict, carrier: dict) -> str:
    """Render a rate confirmation as a self-contained HTML email."""
    fmt_money = lambda v: f"${float(v or 0):,.2f}"
    fmt_rpm   = lambda v: f"${float(v or 0):.2f}/mi" if v else "—"

    rate_total   = fmt_money(load.get("rate_total") or load.get("rate"))
    rate_per_mile = fmt_rpm(load.get("rate_per_mile") or load.get("rpm"))
    dispatch_fee  = fmt_money(load.get("dispatch_fee"))
    dispatch_pct  = load.get("dispatch_pct") or 0

    origin = load.get("origin") or f"{load.get('origin_city','')}, {load.get('origin_state','')}".strip(", ")
    dest   = load.get("destination") or f"{load.get('dest_city','')}, {load.get('dest_state','')}".strip(", ")

    pickup_addr   = load.get("pickup_address") or origin
    delivery_addr = load.get("delivery_address") or dest
    pickup_date   = load.get("pickup_date") or "—"
    commodity     = load.get("commodity") or "General Freight"
    equip_type    = load.get("equipment_type") or "—"
    weight        = f"{load.get('weight_lbs'):,} lbs" if load.get("weight_lbs") else "—"
    miles         = f"{int(load.get('miles') or 0):,}" if load.get("miles") else "—"
    special       = load.get("special_instructions") or ""
    load_number   = load.get("load_number") or "—"
    driver_name   = load.get("driver_name") or "—"
    shipper_name  = load.get("shipper_name") or load.get("notes") or "—"

    carrier_name  = carrier.get("company_name") or driver_name
    carrier_mc    = carrier.get("mc_number") or "—"
    carrier_dot   = carrier.get("dot_number") or "—"

    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    special_block = (
        f'<div style="background:#fffbeb;border-left:4px solid #f59e0b;padding:14px 20px;margin-top:16px;border-radius:4px">'
        f'<div style="font-size:11px;color:#92400e;font-weight:700;text-transform:uppercase;margin-bottom:6px">Special Instructions</div>'
        f'<div style="font-size:14px;color:#78350f">{special}</div></div>'
    ) if special else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rate Confirmation — {load_number}</title>
<style>
  body{{font-family:Arial,Helvetica,sans-serif;margin:0;padding:0;background:#f1f5f9;color:#1e293b}}
  .wrap{{max-width:650px;margin:24px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.08)}}
  .hdr{{background:#0f172a;padding:28px 30px;color:#fff}}
  .hdr-logo{{font-size:20px;font-weight:800;letter-spacing:-.5px}}
  .hdr-sub{{font-size:11px;color:#94a3b8;margin-top:4px;letter-spacing:2px;text-transform:uppercase}}
  .banner{{background:#0ea5e9;color:#fff;padding:14px 30px;font-size:13px;font-weight:600;display:flex;justify-content:space-between;align-items:center}}
  .section{{padding:20px 30px;border-bottom:1px solid #e2e8f0}}
  .section:last-of-type{{border-bottom:none}}
  .sec-title{{font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:14px}}
  .grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
  .grid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}}
  .field .lbl{{font-size:10px;color:#94a3b8;font-weight:700;text-transform:uppercase;margin-bottom:4px}}
  .field .val{{font-size:14px;font-weight:600;color:#1e293b}}
  .rate-box{{background:#f0fdf4;border:2px solid #bbf7d0;border-radius:8px;padding:20px 24px;text-align:center}}
  .rate-big{{font-size:36px;font-weight:800;color:#16a34a;line-height:1}}
  .rate-sub{{font-size:12px;color:#4ade80;margin-top:6px}}
  .signature-box{{background:#f8fafc;border:1px dashed #cbd5e1;border-radius:6px;padding:16px 20px;margin-top:16px}}
  .signature-box .lbl{{font-size:10px;color:#94a3b8;font-weight:700;text-transform:uppercase;margin-bottom:10px}}
  .sig-line{{border-bottom:1px solid #94a3b8;margin-bottom:6px;height:32px}}
  .footer{{background:#f8fafc;padding:16px 30px;text-align:center;font-size:11px;color:#94a3b8;line-height:1.6}}
</style>
</head>
<body>
<div class="wrap">

  <div class="hdr">
    <div class="hdr-logo">3 Lakes Logistics</div>
    <div class="hdr-sub">Rate Confirmation</div>
  </div>

  <div class="banner">
    <span>Load {load_number}</span>
    <span>Issued {today}</span>
  </div>

  <div class="section">
    <div class="sec-title">Rate</div>
    <div class="grid">
      <div class="rate-box">
        <div class="rate-big">{rate_total}</div>
        <div class="rate-sub">{rate_per_mile} &nbsp;·&nbsp; {miles} miles</div>
      </div>
      <div style="display:flex;flex-direction:column;gap:12px">
        <div class="field"><div class="lbl">Dispatch Fee ({dispatch_pct}%)</div><div class="val">{dispatch_fee}</div></div>
        <div class="field"><div class="lbl">Equipment</div><div class="val">{equip_type}</div></div>
        <div class="field"><div class="lbl">Weight</div><div class="val">{weight}</div></div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="sec-title">Lane</div>
    <div class="grid">
      <div class="field"><div class="lbl">Pickup</div><div class="val">{origin}</div>
        <div style="font-size:12px;color:#64748b;margin-top:4px">{pickup_addr}</div>
        <div style="font-size:12px;color:#64748b">Date: {pickup_date}</div>
      </div>
      <div class="field"><div class="lbl">Delivery</div><div class="val">{dest}</div>
        <div style="font-size:12px;color:#64748b;margin-top:4px">{delivery_addr}</div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="sec-title">Commodity</div>
    <div class="field"><div class="val">{commodity}</div></div>
    {special_block}
  </div>

  <div class="section">
    <div class="sec-title">Carrier</div>
    <div class="grid3">
      <div class="field"><div class="lbl">Company</div><div class="val">{carrier_name}</div></div>
      <div class="field"><div class="lbl">MC Number</div><div class="val">{carrier_mc}</div></div>
      <div class="field"><div class="lbl">DOT Number</div><div class="val">{carrier_dot}</div></div>
    </div>
    <div style="margin-top:14px" class="field"><div class="lbl">Driver / Contact</div><div class="val">{driver_name}</div></div>
  </div>

  <div class="section">
    <div class="sec-title">Shipper / Broker</div>
    <div class="field"><div class="val">{shipper_name}</div></div>
  </div>

  <div class="section">
    <div class="sec-title">Carrier Acknowledgement</div>
    <p style="font-size:13px;color:#475569;margin:0 0 12px">By signing below the carrier agrees to the rate and terms stated above.</p>
    <div class="grid">
      <div>
        <div class="signature-box">
          <div class="lbl">Authorized Signature</div>
          <div class="sig-line"></div>
        </div>
      </div>
      <div>
        <div class="signature-box">
          <div class="lbl">Date</div>
          <div class="sig-line"></div>
        </div>
      </div>
    </div>
  </div>

  <div class="footer">
    3 Lakes Logistics &nbsp;·&nbsp; info@3lakeslogistics.com<br>
    This rate confirmation is binding upon carrier acceptance.
  </div>

</div>
</body>
</html>"""


@router.post("/loads/{load_id}/send-rate-con")
def send_rate_con(load_id: str) -> dict:
    """Generate a rate confirmation and email it to the carrier."""
    sb = get_supabase()
    s  = get_settings()

    # Fetch load
    load_res = sb.table("loads").select("*").eq("id", load_id).maybe_single().execute()
    if not load_res.data:
        raise HTTPException(404, "load not found")
    load = load_res.data

    # Find carrier: try carrier_id first, then match by company_name
    carrier: dict = {}
    carrier_id = load.get("carrier_id")
    if carrier_id:
        cr = sb.table("active_carriers").select("*").eq("id", carrier_id).maybe_single().execute()
        if cr.data:
            carrier = cr.data

    # Determine recipient email — prefer broker_email for rate cons going to broker,
    # carrier email for rate cons going to the carrier
    to_email = (
        load.get("broker_email")
        or carrier.get("email")
        or ""
    )

    if not to_email:
        raise HTTPException(422, "no email address on file — add broker_email or carrier email")

    html_body = _build_rate_con_html(load, carrier)
    load_number = load.get("load_number") or load_id

    sent = False
    error_msg = ""
    if s.postmark_server_token:
        try:
            from postmarker.core import PostmarkClient  # type: ignore
            PostmarkClient(server_token=s.postmark_server_token).emails.send(
                From=s.postmark_from_email,
                To=to_email,
                Subject=f"Rate Confirmation — {load_number} | 3 Lakes Logistics",
                HtmlBody=html_body,
                TextBody=(
                    f"Rate Confirmation — {load_number}\n\n"
                    f"Lane: {load.get('origin','?')} → {load.get('destination','?')}\n"
                    f"Rate: ${float(load.get('rate_total') or load.get('rate') or 0):,.2f}\n"
                    f"Pickup: {load.get('pickup_date','TBD')}\n\n"
                    "— 3 Lakes Logistics"
                ),
            )
            sent = True
        except Exception as e:  # noqa: BLE001
            log.error("postmark send failed: %s", e)
            error_msg = str(e)
    else:
        log.warning("postmark_server_token not configured — rate con not emailed")

    # Stamp load record regardless (tracks attempt)
    try:
        sb.table("loads").update({
            "rate_con_sent_at": _NOW(),
            "rate_con_sent_to": to_email,
        }).eq("id", load_id).execute()
    except Exception as e:  # noqa: BLE001
        log.error("failed to stamp rate_con_sent_at: %s", e)

    # Log to document_vault
    try:
        sb.table("document_vault").insert({
            "carrier_id":    str(carrier_id) if carrier_id else None,
            "doc_type":      "rate_con",
            "filename":      f"rate_con_{load_number}.html",
            "storage_path":  f"rate_cons/{load_id}.html",
            "mime_type":     "text/html",
            "scan_status":   "complete",
            "scan_result":   {"load_id": load_id, "sent_to": to_email, "sent": sent},
        }).execute()
    except Exception as e:  # noqa: BLE001
        log.warning("document_vault insert failed (non-fatal): %s", e)

    if not sent and not s.postmark_server_token:
        return {"ok": True, "sent": False, "note": "postmark_not_configured",
                "would_send_to": to_email, "html_preview": html_body[:500]}

    if not sent:
        raise HTTPException(502, f"email delivery failed: {error_msg}")

    return {"ok": True, "sent": True, "to": to_email, "load_number": load_number}


@router.get("/loads/{load_id}/rate-con-preview")
def preview_rate_con(load_id: str) -> dict:
    """Return the rate confirmation HTML for preview in Eagle Eye."""
    sb = get_supabase()

    load_res = sb.table("loads").select("*").eq("id", load_id).maybe_single().execute()
    if not load_res.data:
        raise HTTPException(404, "load not found")
    load = load_res.data

    carrier: dict = {}
    carrier_id = load.get("carrier_id")
    if carrier_id:
        cr = sb.table("active_carriers").select("*").eq("id", carrier_id).maybe_single().execute()
        if cr.data:
            carrier = cr.data

    html = _build_rate_con_html(load, carrier)
    to_email = (
        load.get("broker_email")
        or carrier.get("email")
        or ""
    )
    return {"ok": True, "html": html, "to_email": to_email,
            "already_sent": bool(load.get("rate_con_sent_at")),
            "sent_at": load.get("rate_con_sent_at"),
            "sent_to": load.get("rate_con_sent_to")}

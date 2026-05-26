"""Invoicing + AR Tracking — dedicated routes beyond the dashboard CRUD."""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException

from ..logging_service import get_logger
from ..settings import get_settings
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("route.invoices")
router = APIRouter(dependencies=[Depends(require_bearer)])

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _build_invoice_html(inv: dict, customer: dict, load: dict) -> str:
    fmt  = lambda v: f"${float(v or 0):,.2f}"
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    due   = inv.get("due_date") or "—"
    status_color = {"Paid": "#16a34a", "Overdue": "#dc2626", "Partial": "#d97706"}.get(inv.get("status","Unpaid"), "#64748b")

    load_row = ""
    if load:
        origin = load.get("origin") or f"{load.get('origin_city','')}, {load.get('origin_state','')}".strip(", ")
        dest   = load.get("destination") or f"{load.get('dest_city','')}, {load.get('dest_state','')}".strip(", ")
        load_row = f"""
        <tr>
          <td style="padding:10px 14px;font-size:13px">{load.get('load_number','—')}</td>
          <td style="padding:10px 14px;font-size:13px">{origin} → {dest}</td>
          <td style="padding:10px 14px;font-size:13px">{load.get('pickup_date','—')}</td>
          <td style="padding:10px 14px;font-size:13px;font-weight:600;text-align:right">{fmt(load.get('rate_total') or load.get('rate'))}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Invoice {inv.get('invoice_number','—')}</title>
<style>
  body{{font-family:Arial,Helvetica,sans-serif;margin:0;padding:0;background:#f1f5f9;color:#1e293b}}
  .wrap{{max-width:680px;margin:24px auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.08)}}
  .hdr{{background:#0f172a;padding:28px 32px;color:#fff;display:flex;justify-content:space-between;align-items:flex-start}}
  .hdr-logo{{font-size:20px;font-weight:800;letter-spacing:-.5px}}
  .hdr-sub{{font-size:11px;color:#94a3b8;margin-top:4px;letter-spacing:2px;text-transform:uppercase}}
  .inv-meta{{text-align:right}}
  .inv-num{{font-size:22px;font-weight:800;color:#fbbf24}}
  .inv-date{{font-size:11px;color:#94a3b8;margin-top:4px}}
  .status-bar{{padding:10px 32px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#fff;background:{status_color}}}
  .body{{padding:28px 32px}}
  .billing-row{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px}}
  .billing-block .lbl{{font-size:10px;color:#94a3b8;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}}
  .billing-block .val{{font-size:14px;font-weight:600}}
  .billing-block .sub{{font-size:12px;color:#64748b;margin-top:2px}}
  table{{width:100%;border-collapse:collapse;margin-bottom:20px}}
  thead tr{{background:#f8fafc;border-bottom:2px solid #e2e8f0}}
  thead th{{padding:10px 14px;font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;text-align:left}}
  tbody tr{{border-bottom:1px solid #f1f5f9}}
  .total-row{{background:#f8fafc;border-top:2px solid #e2e8f0}}
  .due-box{{background:#f0fdf4;border:2px solid #bbf7d0;border-radius:8px;padding:20px 24px;display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}}
  .due-label{{font-size:13px;color:#166534;font-weight:600}}
  .due-amount{{font-size:32px;font-weight:800;color:#16a34a}}
  .terms{{background:#f8fafc;border-radius:6px;padding:14px 18px;font-size:12px;color:#64748b;margin-bottom:20px}}
  .footer{{background:#f8fafc;padding:16px 32px;text-align:center;font-size:11px;color:#94a3b8}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hdr">
    <div>
      <div class="hdr-logo">3 Lakes Logistics</div>
      <div class="hdr-sub">Invoice</div>
    </div>
    <div class="inv-meta">
      <div class="inv-num">{inv.get('invoice_number','INV-0000')}</div>
      <div class="inv-date">Issued {today}</div>
    </div>
  </div>
  <div class="status-bar">Status: {inv.get('status','Unpaid')}</div>
  <div class="body">
    <div class="billing-row">
      <div class="billing-block">
        <div class="lbl">Bill To</div>
        <div class="val">{customer.get('company_name','—')}</div>
        <div class="sub">{customer.get('contact_name','')}</div>
        <div class="sub">{customer.get('email','')}</div>
      </div>
      <div class="billing-block">
        <div class="lbl">From</div>
        <div class="val">3 Lakes Logistics LLC</div>
        <div class="sub">info@3lakeslogistics.com</div>
        <div class="sub">661-466-9932</div>
      </div>
    </div>
    {f'<table><thead><tr><th>Load #</th><th>Lane</th><th>Pickup</th><th style="text-align:right">Amount</th></tr></thead><tbody>{load_row}</tbody></table>' if load_row else ''}
    <div class="due-box">
      <div class="due-label">Amount Due &nbsp; · &nbsp; Due {due}</div>
      <div class="due-amount">{fmt(inv.get('amount'))}</div>
    </div>
    <div class="terms">
      <strong>Payment Terms:</strong> {inv.get('payment_terms','Net 30').replace('_',' ').upper()}<br>
      {f"<strong>Notes:</strong> {inv.get('notes')}" if inv.get('notes') else ''}
    </div>
  </div>
  <div class="footer">3 Lakes Logistics LLC &nbsp;·&nbsp; info@3lakeslogistics.com &nbsp;·&nbsp; 661-466-9932<br>
  Thank you for your business. Payment due by {due}.</div>
</div>
</body>
</html>"""


@router.get("/invoices/aging")
def ar_aging() -> dict:
    """AR aging buckets: 0-30, 31-60, 61-90, 90+ days past due."""
    sb = get_supabase()
    # Auto-refresh overdue status first
    try:
        sb.rpc("refresh_overdue_invoices", {}).execute()
    except Exception:  # noqa: BLE001
        pass
    res = sb.table("invoices").select("*").neq("status", "Paid").execute()
    rows = res.data or []
    today = date.today()
    buckets: dict[str, list] = {"current": [], "1_30": [], "31_60": [], "61_90": [], "91_plus": []}
    for r in rows:
        due = r.get("due_date")
        if not due:
            buckets["current"].append(r); continue
        try:
            due_dt = date.fromisoformat(due[:10])
            days_past = (today - due_dt).days
        except ValueError:
            buckets["current"].append(r); continue
        if days_past <= 0:
            buckets["current"].append(r)
        elif days_past <= 30:
            buckets["1_30"].append(r)
        elif days_past <= 60:
            buckets["31_60"].append(r)
        elif days_past <= 90:
            buckets["61_90"].append(r)
        else:
            buckets["91_plus"].append(r)

    def _sum(lst): return sum(float(r.get("amount") or 0) for r in lst)
    return {
        "total_outstanding": _sum(rows),
        "buckets": {k: {"count": len(v), "total": _sum(v), "items": v} for k, v in buckets.items()},
    }


@router.post("/invoices/{invoice_id}/send")
def send_invoice(invoice_id: str) -> dict:
    """Generate branded HTML invoice and email to the customer."""
    sb = get_supabase()
    s  = get_settings()

    inv_res = sb.table("invoices").select("*").eq("id", invoice_id).maybe_single().execute()
    if not inv_res.data:
        raise HTTPException(404, "invoice not found")
    inv = inv_res.data

    # Fetch customer
    customer: dict = {}
    if inv.get("customer_id"):
        cr = sb.table("customers").select("*").eq("id", inv["customer_id"]).maybe_single().execute()
        if cr.data:
            customer = cr.data

    # Fetch linked load
    load: dict = {}
    if inv.get("load_id"):
        lr = sb.table("loads").select("*").eq("id", inv["load_id"]).maybe_single().execute()
        if lr.data:
            load = lr.data

    to_email = customer.get("email") or ""
    if not to_email:
        raise HTTPException(422, "no email on file for customer — update customer record")

    html = _build_invoice_html(inv, customer, load)
    inv_num = inv.get("invoice_number") or invoice_id[:8]

    sent = False
    if s.postmark_server_token:
        try:
            from postmarker.core import PostmarkClient  # type: ignore
            PostmarkClient(server_token=s.postmark_server_token).emails.send(
                From=s.postmark_from_email,
                To=to_email,
                Subject=f"Invoice {inv_num} — ${float(inv.get('amount') or 0):,.2f} | 3 Lakes Logistics",
                HtmlBody=html,
                TextBody=(
                    f"Invoice {inv_num}\n"
                    f"Amount Due: ${float(inv.get('amount') or 0):,.2f}\n"
                    f"Due: {inv.get('due_date','—')}\n"
                    f"Status: {inv.get('status','Unpaid')}\n\n"
                    "— 3 Lakes Logistics · info@3lakeslogistics.com"
                ),
            )
            sent = True
        except Exception as e:  # noqa: BLE001
            log.error("invoice email failed: %s", e)
            raise HTTPException(502, f"email delivery failed: {e}")
    else:
        log.warning("postmark_server_token not configured")

    try:
        sb.table("invoices").update({"sent_at": _NOW(), "sent_to": to_email}).eq("id", invoice_id).execute()
    except Exception as e:  # noqa: BLE001
        log.warning("failed to stamp sent_at: %s", e)

    return {"ok": True, "sent": sent, "to": to_email, "invoice_number": inv_num}


@router.get("/invoices/{invoice_id}/preview")
def preview_invoice(invoice_id: str) -> dict:
    """Return HTML invoice for Eagle Eye iframe preview."""
    sb = get_supabase()
    inv_res = sb.table("invoices").select("*").eq("id", invoice_id).maybe_single().execute()
    if not inv_res.data:
        raise HTTPException(404, "invoice not found")
    inv = inv_res.data
    customer: dict = {}
    if inv.get("customer_id"):
        cr = sb.table("customers").select("*").eq("id", inv["customer_id"]).maybe_single().execute()
        if cr.data: customer = cr.data
    load: dict = {}
    if inv.get("load_id"):
        lr = sb.table("loads").select("*").eq("id", inv["load_id"]).maybe_single().execute()
        if lr.data: load = lr.data
    html = _build_invoice_html(inv, customer, load)
    to_email = customer.get("email") or ""
    return {"ok": True, "html": html, "to_email": to_email,
            "already_sent": bool(inv.get("sent_at")),
            "sent_at": inv.get("sent_at"), "sent_to": inv.get("sent_to")}

"""Driver weekly settlement statements.

Endpoints:
  GET  /api/settlements              — list settlements
  GET  /api/settlements/weekly-preview — aggregate delivered loads into weekly preview
  POST /api/settlements/generate     — create a driver_settlements record
  POST /api/settlements/{id}/send    — send HTML statement via Postmark
  GET  /api/settlements/{id}/preview — HTML preview for iframe
"""
from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..supabase_client import get_supabase
from ..settings import get_settings
from ..logging_service import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/settlements", tags=["settlements"])


# ─────────────────────────────────────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────────────────────────────────────

class GenerateSettlementRequest(BaseModel):
    driver_id: str
    week_start: str          # ISO date string  e.g. "2025-05-19"
    dispatch_fee_pct: float  = 0.08   # 8% default
    fuel_advance: float      = 0.0
    insurance_per_load: float = 45.0
    other_deductions: float  = 0.0
    notes: Optional[str]     = None


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _week_bounds(week_start_str: str) -> tuple[datetime.date, datetime.date]:
    """Return (monday, sunday) for the ISO week containing week_start_str."""
    d = datetime.date.fromisoformat(week_start_str)
    monday = d - datetime.timedelta(days=d.weekday())
    sunday = monday + datetime.timedelta(days=6)
    return monday, sunday


def _fmt(val) -> str:
    try:
        return f"${float(val):,.2f}"
    except Exception:
        return "$0.00"


def _build_statement_html(settlement: dict, loads: list[dict]) -> str:
    driver_name  = settlement.get("driver_name") or "Driver"
    week_start   = settlement.get("week_start") or ""
    week_end     = settlement.get("week_end") or ""
    gross        = float(settlement.get("gross_pay") or 0)
    dispatch_fee = float(settlement.get("dispatch_fee") or 0)
    fuel_adv     = float(settlement.get("fuel_advance") or 0)
    insurance    = float(settlement.get("insurance_deduction") or 0)
    other_ded    = float(settlement.get("other_deductions") or 0)
    net          = float(settlement.get("net_pay") or 0)
    load_count   = settlement.get("load_count") or len(loads)
    total_miles  = settlement.get("total_miles") or 0

    load_rows = ""
    for ld in loads:
        origin  = f"{ld.get('origin_city','')}, {ld.get('origin_state','')}".strip(", ")
        dest    = f"{ld.get('dest_city','')}, {ld.get('dest_state','')}".strip(", ")
        rate    = float(ld.get("rate_total") or 0)
        miles   = int(ld.get("miles") or 0)
        pu_date = (ld.get("pickup_at") or "")[:10]
        load_rows += f"""
        <tr>
          <td>{ld.get('load_number','—')}</td>
          <td>{pu_date}</td>
          <td>{origin or '—'}</td>
          <td>{dest or '—'}</td>
          <td style="text-align:right">{miles:,}</td>
          <td style="text-align:right;font-weight:600">${rate:,.2f}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',Arial,sans-serif;background:#f5f6fa;color:#0a0f1e;font-size:14px}}
  .page{{max-width:780px;margin:0 auto;background:#fff;padding:40px;border-radius:12px}}
  .hdr{{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:32px;padding-bottom:20px;border-bottom:3px solid #e8b84b}}
  .logo{{font-size:22px;font-weight:900;color:#0a1628;letter-spacing:-0.5px}}
  .logo span{{color:#e8b84b}}
  .hdr-right{{text-align:right;font-size:12px;color:#6b7280}}
  .title{{font-size:20px;font-weight:800;color:#0a1628;margin-bottom:4px}}
  .period{{font-size:13px;color:#6b7280}}
  .meta{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:28px}}
  .meta-box{{background:#f5f6fa;border-radius:8px;padding:14px}}
  .meta-label{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:#6b7280;margin-bottom:4px}}
  .meta-val{{font-size:18px;font-weight:800;color:#0a1628}}
  table{{width:100%;border-collapse:collapse;margin-bottom:24px}}
  th{{background:#0a1628;color:#fff;padding:9px 12px;text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
  td{{padding:9px 12px;border-bottom:1px solid #f0f1f5;font-size:13px}}
  tr:last-child td{{border-bottom:none}}
  tr:hover td{{background:#f9fafb}}
  .totals{{background:#f5f6fa;border-radius:10px;padding:20px;margin-bottom:24px}}
  .totals-row{{display:flex;justify-content:space-between;padding:6px 0;font-size:13px;border-bottom:1px solid #e5e7eb}}
  .totals-row:last-child{{border-bottom:none;padding-top:14px;font-size:16px;font-weight:800}}
  .totals-row.deduct{{color:#dc2626}}
  .net-box{{background:#0a1628;color:#fff;border-radius:10px;padding:20px 24px;display:flex;justify-content:space-between;align-items:center;margin-bottom:28px}}
  .net-label{{font-size:13px;opacity:.7;text-transform:uppercase;letter-spacing:.06em}}
  .net-amount{{font-size:32px;font-weight:900;color:#e8b84b}}
  .sig{{margin-top:28px;padding-top:20px;border-top:1px solid #e5e7eb;display:grid;grid-template-columns:1fr 1fr;gap:32px}}
  .sig-line{{border-bottom:1px solid #0a1628;margin-bottom:6px;height:32px}}
  .sig-label{{font-size:11px;color:#6b7280}}
  .footer{{text-align:center;font-size:11px;color:#9ca3af;margin-top:28px;padding-top:20px;border-top:1px solid #f0f1f5}}
  @media print{{body{{background:#fff}}.page{{box-shadow:none}}}}
</style>
</head>
<body>
<div class="page">
  <div class="hdr">
    <div>
      <div class="logo">3 <span>Lakes</span> Logistics</div>
      <div style="font-size:12px;color:#6b7280;margin-top:4px">Dispatch Services Agreement</div>
    </div>
    <div class="hdr-right">
      <div class="title">Weekly Settlement Statement</div>
      <div class="period">Pay Period: {week_start} — {week_end}</div>
    </div>
  </div>

  <div class="meta">
    <div class="meta-box">
      <div class="meta-label">Driver</div>
      <div class="meta-val">{driver_name}</div>
    </div>
    <div class="meta-box">
      <div class="meta-label">Loads Delivered</div>
      <div class="meta-val">{load_count}</div>
    </div>
    <div class="meta-box">
      <div class="meta-label">Total Miles</div>
      <div class="meta-val">{int(total_miles):,}</div>
    </div>
  </div>

  <table>
    <thead>
      <tr><th>Load #</th><th>Pickup Date</th><th>Origin</th><th>Destination</th><th style="text-align:right">Miles</th><th style="text-align:right">Gross Rate</th></tr>
    </thead>
    <tbody>
      {load_rows if load_rows else '<tr><td colspan="6" style="text-align:center;color:#6b7280;padding:20px">No loads for this period</td></tr>'}
    </tbody>
  </table>

  <div class="totals">
    <div class="totals-row"><span>Gross Pay (from loads)</span><span style="font-weight:600">{_fmt(gross)}</span></div>
    <div class="totals-row deduct"><span>Dispatch Fee ({int(dispatch_fee/gross*100) if gross else 8}%)</span><span>− {_fmt(dispatch_fee)}</span></div>
    <div class="totals-row deduct"><span>Fuel Advance</span><span>− {_fmt(fuel_adv)}</span></div>
    <div class="totals-row deduct"><span>Insurance Deduction</span><span>− {_fmt(insurance)}</span></div>
    {"<div class='totals-row deduct'><span>Other Deductions</span><span>− " + _fmt(other_ded) + "</span></div>" if other_ded else ""}
    <div class="totals-row"><span style="font-weight:800">NET PAY</span><span style="color:#16a34a;font-size:18px;font-weight:900">{_fmt(net)}</span></div>
  </div>

  <div class="net-box">
    <div><div class="net-label">Net Pay This Week</div><div style="font-size:12px;opacity:.5;margin-top:2px">{driver_name} · {week_start} to {week_end}</div></div>
    <div class="net-amount">{_fmt(net)}</div>
  </div>

  <div class="sig">
    <div><div class="sig-line"></div><div class="sig-label">Driver Signature / Date</div></div>
    <div><div class="sig-line"></div><div class="sig-label">Dispatcher Signature / Date</div></div>
  </div>

  <div class="footer">
    3 Lakes Logistics LLC · Dispatch Services · new56money@gmail.com<br>
    This document is a record of dispatch services rendered and deductions applied for the stated pay period.
  </div>
</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("")
def list_settlements(
    driver_id: Optional[str] = Query(None),
    carrier_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """List settlement statements with optional filters."""
    sb = get_supabase()
    try:
        q = sb.table("driver_settlements").select("*").order("week_start", desc=True).limit(limit)
        if driver_id:
            q = q.eq("driver_id", driver_id)
        if carrier_id:
            q = q.eq("carrier_id", carrier_id)
        if status:
            q = q.eq("status", status)
        r = q.execute()
        return {"ok": True, "settlements": r.data or []}
    except Exception as e:
        log.error("list_settlements error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/weekly-preview")
def weekly_preview(
    driver_id: str = Query(...),
    week_start: str = Query(...),
    dispatch_fee_pct: float = Query(0.08),
    insurance_per_load: float = Query(45.0),
):
    """Preview what a weekly settlement would look like without saving."""
    sb = get_supabase()
    try:
        monday, sunday = _week_bounds(week_start)

        driver_r = sb.table("drivers").select(
            "id, first_name, last_name, carrier_id"
        ).eq("id", driver_id).maybe_single().execute()
        driver = driver_r.data or {}
        driver_name = f"{driver.get('first_name','')} {driver.get('last_name','')}".strip() or "Driver"

        loads_r = sb.table("loads").select("*").eq("driver_id", driver_id).eq(
            "status", "delivered"
        ).gte("pickup_at", monday.isoformat()).lte("pickup_at", (sunday + datetime.timedelta(days=1)).isoformat()).execute()
        loads = loads_r.data or []

        gross = sum(float(l.get("rate_total") or 0) for l in loads)
        miles = sum(int(l.get("miles") or 0) for l in loads)
        dispatch_fee = round(gross * dispatch_fee_pct, 2)
        insurance = round(len(loads) * insurance_per_load, 2)
        net = round(gross - dispatch_fee - insurance, 2)

        return {
            "ok": True,
            "driver_name": driver_name,
            "driver_id": driver_id,
            "carrier_id": driver.get("carrier_id"),
            "week_start": monday.isoformat(),
            "week_end": sunday.isoformat(),
            "load_count": len(loads),
            "total_miles": miles,
            "gross_pay": gross,
            "dispatch_fee": dispatch_fee,
            "insurance_deduction": insurance,
            "net_pay": net,
            "loads": loads,
        }
    except Exception as e:
        log.error("weekly_preview error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
def generate_settlement(req: GenerateSettlementRequest):
    """Create a driver_settlements record aggregating the driver's delivered loads for the week."""
    sb = get_supabase()
    try:
        monday, sunday = _week_bounds(req.week_start)

        existing_r = sb.table("driver_settlements").select("id").eq(
            "driver_id", req.driver_id
        ).eq("week_start", monday.isoformat()).execute()
        if existing_r.data:
            raise HTTPException(status_code=409, detail="settlement already exists for this driver/week")

        driver_r = sb.table("drivers").select(
            "id, first_name, last_name, carrier_id, email"
        ).eq("id", req.driver_id).maybe_single().execute()
        driver = driver_r.data or {}
        driver_name = f"{driver.get('first_name','')} {driver.get('last_name','')}".strip() or "Driver"

        loads_r = sb.table("loads").select("*").eq("driver_id", req.driver_id).eq(
            "status", "delivered"
        ).gte("pickup_at", monday.isoformat()).lte("pickup_at", (sunday + datetime.timedelta(days=1)).isoformat()).execute()
        loads = loads_r.data or []
        load_ids = [l["id"] for l in loads]

        gross = sum(float(l.get("rate_total") or 0) for l in loads)
        miles = sum(int(l.get("miles") or 0) for l in loads)
        dispatch_fee = round(gross * req.dispatch_fee_pct, 2)
        insurance = round(len(loads) * req.insurance_per_load, 2)
        net = round(gross - dispatch_fee - req.fuel_advance - insurance - req.other_deductions, 2)

        ins_r = sb.table("driver_settlements").insert({
            "driver_id": req.driver_id,
            "carrier_id": driver.get("carrier_id"),
            "driver_name": driver_name,
            "week_start": monday.isoformat(),
            "week_end": sunday.isoformat(),
            "load_count": len(loads),
            "total_miles": miles,
            "gross_pay": gross,
            "dispatch_fee": dispatch_fee,
            "fuel_advance": req.fuel_advance,
            "insurance_deduction": insurance,
            "other_deductions": req.other_deductions,
            "net_pay": net,
            "status": "draft",
            "load_ids": load_ids,
            "notes": req.notes,
            "sent_to": driver.get("email"),
        }).execute()

        settlement_id = ins_r.data[0]["id"] if ins_r.data else None
        return {
            "ok": True,
            "settlement_id": settlement_id,
            "driver_name": driver_name,
            "week_start": monday.isoformat(),
            "week_end": sunday.isoformat(),
            "load_count": len(loads),
            "gross_pay": gross,
            "net_pay": net,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("generate_settlement error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{settlement_id}/preview")
def preview_settlement(settlement_id: str):
    """Return HTML settlement statement for iframe preview."""
    sb = get_supabase()
    try:
        r = sb.table("driver_settlements").select("*").eq("id", settlement_id).maybe_single().execute()
        settlement = r.data
        if not settlement:
            raise HTTPException(status_code=404, detail="settlement not found")

        loads: list[dict] = []
        load_ids = settlement.get("load_ids") or []
        if load_ids:
            ldr = sb.table("loads").select(
                "load_number,pickup_at,origin_city,origin_state,dest_city,dest_state,rate_total,miles"
            ).in_("id", load_ids).execute()
            loads = ldr.data or []

        html = _build_statement_html(settlement, loads)
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html)
    except HTTPException:
        raise
    except Exception as e:
        log.error("preview_settlement error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{settlement_id}/send")
def send_settlement(settlement_id: str):
    """Generate HTML statement and email it to the driver via Postmark."""
    sb = get_supabase()
    s = get_settings()
    try:
        r = sb.table("driver_settlements").select("*").eq("id", settlement_id).maybe_single().execute()
        settlement = r.data
        if not settlement:
            raise HTTPException(status_code=404, detail="settlement not found")

        driver_email = settlement.get("sent_to")
        if not driver_email and settlement.get("driver_id"):
            dr = sb.table("drivers").select("email").eq("id", settlement["driver_id"]).maybe_single().execute()
            driver_email = (dr.data or {}).get("email")

        if not driver_email:
            raise HTTPException(status_code=400, detail="no driver email on file")

        loads: list[dict] = []
        load_ids = settlement.get("load_ids") or []
        if load_ids:
            ldr = sb.table("loads").select(
                "load_number,pickup_at,origin_city,origin_state,dest_city,dest_state,rate_total,miles"
            ).in_("id", load_ids).execute()
            loads = ldr.data or []

        html = _build_statement_html(settlement, loads)

        driver_name  = settlement.get("driver_name") or "Driver"
        week_start   = settlement.get("week_start") or ""
        net_pay      = float(settlement.get("net_pay") or 0)
        subject      = f"Settlement Statement — Week of {week_start} — Net ${net_pay:,.2f}"

        if s.postmark_server_token:
            from postmarker.core import PostmarkClient  # type: ignore
            PostmarkClient(server_token=s.postmark_server_token).emails.send(
                From=s.postmark_from_email,
                To=driver_email,
                Subject=subject,
                HtmlBody=html,
            )
        else:
            log.warning("Postmark not configured — settlement email not sent to %s", driver_email)

        import datetime as _dt
        sb.table("driver_settlements").update({
            "status": "sent",
            "sent_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "sent_to": driver_email,
        }).eq("id", settlement_id).execute()

        log.info("settlement %s sent to %s", settlement_id, driver_email)
        return {"ok": True, "sent_to": driver_email, "subject": subject, "net_pay": net_pay}
    except HTTPException:
        raise
    except Exception as e:
        log.error("send_settlement error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{settlement_id}/acknowledge")
def acknowledge_settlement(settlement_id: str):
    """Driver acknowledges receipt — updates status to 'acknowledged'."""
    sb = get_supabase()
    try:
        sb.table("driver_settlements").update({"status": "acknowledged"}).eq(
            "id", settlement_id
        ).execute()
        return {"ok": True, "status": "acknowledged"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

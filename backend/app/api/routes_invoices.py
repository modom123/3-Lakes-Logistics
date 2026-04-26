"""Invoices — carrier billing, aging, and payment tracking.

Routes:
  POST   /api/invoices/                    — create invoice (manual or from load)
  POST   /api/invoices/generate-from-load  — auto-generate invoice from a delivered load
  GET    /api/invoices/                    — list (filter by status/carrier/date range)
  GET    /api/invoices/aging               — A/R aging buckets (current/30/60/90+ days)
  GET    /api/invoices/summary             — revenue summary by carrier/period
  GET    /api/invoices/{inv_id}            — single invoice detail
  PATCH  /api/invoices/{inv_id}            — update fields (amount, due_date, notes)
  POST   /api/invoices/{inv_id}/mark-paid  — record payment
  POST   /api/invoices/{inv_id}/mark-overdue — flag overdue
  DELETE /api/invoices/{inv_id}            — void invoice
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])

_DISPATCH_FEE_PCT = 0.08   # 3LL standard dispatch fee


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return date.today().isoformat()


def _due_date(payment_terms: str = "quick_pay_30") -> str:
    days = 30
    if "15" in payment_terms:
        days = 15
    elif "45" in payment_terms:
        days = 45
    elif "60" in payment_terms:
        days = 60
    elif "quick" in payment_terms.lower():
        days = 3
    return (date.today() + timedelta(days=days)).isoformat()


def _next_invoice_number(sb) -> str:
    """Generate next sequential invoice number (INV-YYYYMM-NNNN)."""
    prefix = f"INV-{date.today().strftime('%Y%m')}-"
    res = (
        sb.table("invoices")
        .select("invoice_number")
        .ilike("invoice_number", f"{prefix}%")
        .order("invoice_number", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        last = res.data[0]["invoice_number"]
        try:
            seq = int(last.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_invoice(body: dict) -> dict:
    """Create an invoice manually."""
    sb = get_supabase()
    body.setdefault("status", "Unpaid")
    body.setdefault("invoice_number", _next_invoice_number(sb))
    body.setdefault("invoice_date", _today())
    if not body.get("due_date"):
        body["due_date"] = _due_date(body.get("payment_terms", "quick_pay_30"))

    res = sb.table("invoices").insert(body).execute()
    if not res.data:
        raise HTTPException(500, "invoice insert failed")
    invoice = res.data[0]
    log_agent("settler", "invoice_created", carrier_id=body.get("carrier_id"),
              payload={"invoice_number": invoice.get("invoice_number"),
                       "amount": body.get("amount")})
    return {"ok": True, "invoice": invoice}


@router.post("/generate-from-load", status_code=status.HTTP_201_CREATED)
def generate_from_load(body: dict) -> dict:
    """Auto-generate invoice from a delivered load record."""
    load_id = body.get("load_id", "")
    if not load_id:
        raise HTTPException(400, "load_id required")

    sb = get_supabase()
    load = sb.table("loads").select("*").eq("id", load_id).maybe_single().execute().data
    if not load:
        raise HTTPException(404, "load not found")
    if load.get("status") not in ("delivered", "pod_needed", "closed"):
        raise HTTPException(409, f"load status is '{load.get('status')}' — must be delivered/closed to invoice")

    # Check not already invoiced
    existing = (
        sb.table("invoices")
        .select("id,invoice_number")
        .eq("load_id", load_id)
        .maybe_single()
        .execute()
        .data
    )
    if existing:
        return {"ok": True, "invoice": existing, "note": "invoice already exists for this load"}

    gross = float(load.get("rate_total") or 0)
    dispatch_fee = round(gross * _DISPATCH_FEE_PCT, 2)

    invoice_data: dict[str, Any] = {
        "carrier_id": load.get("carrier_id"),
        "load_id": load_id,
        "invoice_number": _next_invoice_number(sb),
        "invoice_date": _today(),
        "due_date": _due_date(load.get("payment_terms", "quick_pay_30")),
        "amount": gross,
        "dispatch_fee": dispatch_fee,
        "status": "Unpaid",
        "description": (
            f"Load #{load.get('load_number', load_id[:8])} — "
            f"{load.get('origin_city', '')}, {load.get('origin_state', '')} → "
            f"{load.get('dest_city', '')}, {load.get('dest_state', '')}"
        ),
    }
    res = sb.table("invoices").insert(invoice_data).execute()
    if not res.data:
        raise HTTPException(500, "invoice insert failed")
    invoice = res.data[0]
    log_agent("settler", "invoice_generated", carrier_id=load.get("carrier_id"),
              payload={"invoice_number": invoice.get("invoice_number"), "amount": gross})
    return {"ok": True, "invoice": invoice}


# ── List / aging ──────────────────────────────────────────────────────────────

@router.get("/")
def list_invoices(
    status: str | None = None,
    carrier_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 500,
) -> dict:
    q = (
        get_supabase()
        .table("invoices")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        q = q.eq("status", status)
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if date_from:
        q = q.gte("invoice_date", date_from)
    if date_to:
        q = q.lte("invoice_date", date_to)

    res = q.execute()
    items = res.data or []
    total = sum(float(i.get("amount") or 0) for i in items)
    return {"count": len(items), "total_amount": round(total, 2), "items": items}


@router.get("/aging")
def invoice_aging() -> dict:
    """Accounts-receivable aging report: current / 1-30 / 31-60 / 61-90 / 90+ days."""
    res = (
        get_supabase()
        .table("invoices")
        .select("id,invoice_number,carrier_id,amount,due_date,invoice_date,status")
        .in_("status", ["Unpaid", "Overdue"])
        .execute()
    )
    today = date.today()
    buckets: dict[str, list] = {
        "current": [],     # not yet due
        "1_30":    [],     # 1-30 days overdue
        "31_60":   [],     # 31-60 days overdue
        "61_90":   [],     # 61-90 days overdue
        "over_90": [],     # 90+ days overdue
    }
    for inv in res.data or []:
        if not inv.get("due_date"):
            continue
        due = date.fromisoformat(inv["due_date"])
        days_overdue = (today - due).days
        if days_overdue <= 0:
            buckets["current"].append(inv)
        elif days_overdue <= 30:
            buckets["1_30"].append(inv)
        elif days_overdue <= 60:
            buckets["31_60"].append(inv)
        elif days_overdue <= 90:
            buckets["61_90"].append(inv)
        else:
            buckets["over_90"].append(inv)

    def _bucket_total(items: list) -> float:
        return round(sum(float(i.get("amount") or 0) for i in items), 2)

    return {
        "as_of": today.isoformat(),
        "buckets": {k: {"count": len(v), "total": _bucket_total(v), "items": v}
                    for k, v in buckets.items()},
        "total_outstanding": round(sum(_bucket_total(v) for v in buckets.values()), 2),
    }


@router.get("/summary")
def invoice_summary(
    year: int | None = None,
    month: int | None = None,
    carrier_id: str | None = None,
) -> dict:
    """Revenue summary — total billed, collected, outstanding by period."""
    today = date.today()
    yr = year or today.year
    mo = month or today.month
    period_start = date(yr, mo, 1).isoformat()
    if mo == 12:
        period_end = date(yr + 1, 1, 1).isoformat()
    else:
        period_end = date(yr, mo + 1, 1).isoformat()

    q = (
        get_supabase()
        .table("invoices")
        .select("amount,dispatch_fee,status,carrier_id")
        .gte("invoice_date", period_start)
        .lt("invoice_date", period_end)
    )
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    res = q.execute()
    items = res.data or []

    total_billed = sum(float(i.get("amount") or 0) for i in items)
    total_fees = sum(float(i.get("dispatch_fee") or 0) for i in items)
    collected = sum(float(i.get("amount") or 0) for i in items if i.get("status") == "Paid")
    outstanding = sum(float(i.get("amount") or 0) for i in items if i.get("status") != "Paid")

    return {
        "period": f"{yr}-{mo:02d}",
        "invoice_count": len(items),
        "total_billed": round(total_billed, 2),
        "total_dispatch_fees": round(total_fees, 2),
        "collected": round(collected, 2),
        "outstanding": round(outstanding, 2),
        "collection_rate": round(collected / total_billed * 100, 1) if total_billed else 0,
    }


# ── Single invoice ────────────────────────────────────────────────────────────

@router.get("/{inv_id}")
def get_invoice(inv_id: str) -> dict:
    res = get_supabase().table("invoices").select("*").eq("id", inv_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "invoice not found")
    return res.data


@router.patch("/{inv_id}")
def update_invoice(inv_id: str, body: dict) -> dict:
    # Guard: cannot edit paid/voided invoices
    inv = get_supabase().table("invoices").select("status").eq("id", inv_id).maybe_single().execute().data
    if not inv:
        raise HTTPException(404, "invoice not found")
    if inv.get("status") in ("Paid", "Void"):
        raise HTTPException(409, f"cannot edit a {inv['status']} invoice")
    get_supabase().table("invoices").update(body).eq("id", inv_id).execute()
    return {"ok": True, "inv_id": inv_id}


@router.post("/{inv_id}/mark-paid")
def mark_paid(inv_id: str, body: dict | None = None) -> dict:
    body = body or {}
    update: dict[str, Any] = {
        "status": "Paid",
        "paid_at": body.get("paid_at") or _now(),
    }
    if body.get("payment_ref"):
        update["payment_ref"] = body["payment_ref"]
    if body.get("amount_paid"):
        update["amount_paid"] = float(body["amount_paid"])

    get_supabase().table("invoices").update(update).eq("id", inv_id).execute()
    log_agent("settler", "invoice_paid", payload={"inv_id": inv_id, **update})
    return {"ok": True, "inv_id": inv_id, "status": "Paid"}


@router.post("/{inv_id}/mark-overdue")
def mark_overdue(inv_id: str) -> dict:
    get_supabase().table("invoices").update({"status": "Overdue"}).eq("id", inv_id).execute()
    return {"ok": True, "inv_id": inv_id, "status": "Overdue"}


@router.delete("/{inv_id}")
def void_invoice(inv_id: str) -> dict:
    get_supabase().table("invoices").update({"status": "Void"}).eq("id", inv_id).execute()
    log_agent("settler", "invoice_voided", payload={"inv_id": inv_id})
    return {"ok": True, "inv_id": inv_id, "status": "Void"}

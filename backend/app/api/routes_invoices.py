"""Invoice management — billing records for carriers, payment tracking."""
from __future__ import annotations

from datetime import datetime, date, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from ..logging_service import get_logger
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("invoices.routes")
router = APIRouter(dependencies=[require_bearer()])


class InvoiceCreate(BaseModel):
    carrier_id: str
    load_id: Optional[str] = None
    invoice_number: Optional[str] = None
    amount: float
    description: Optional[str] = None
    due_date: date
    payment_method: Optional[str] = None
    notes: Optional[str] = None


class InvoiceUpdate(BaseModel):
    status: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[date] = None
    paid_at: Optional[str] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None


@router.post("")
async def create_invoice(payload: InvoiceCreate) -> dict:
    """Create a new invoice for a carrier.

    Amount in USD. Due date should be future date.
    """
    try:
        sb = get_supabase()

        # Generate invoice number if not provided
        inv_number = payload.invoice_number or f"INV-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        data = {
            "carrier_id": payload.carrier_id,
            "load_id": payload.load_id,
            "invoice_number": inv_number,
            "amount": payload.amount,
            "description": payload.description,
            "due_date": payload.due_date.isoformat(),
            "payment_method": payload.payment_method,
            "notes": payload.notes,
            "status": "unpaid",
            "issued_at": datetime.now(timezone.utc).isoformat(),
        }

        result = sb.table("invoices").insert(data).execute()

        if not result.data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "failed to create invoice")

        return {
            "ok": True,
            "invoice": result.data[0],
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to create invoice: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("")
async def list_invoices(
    carrier_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """List invoices with optional carrier and status filters.

    Status: unpaid, paid, overdue, cancelled
    """
    try:
        sb = get_supabase()

        query = sb.table("invoices").select("*")

        if carrier_id:
            query = query.eq("carrier_id", carrier_id)

        if status_filter:
            query = query.eq("status", status_filter)

        result = (
            query
            .order("issued_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        # Add days_overdue calculation
        for inv in result.data or []:
            inv["days_overdue"] = 0
            if inv.get("status") in ("unpaid", "overdue") and inv.get("due_date"):
                due = datetime.fromisoformat(inv["due_date"]).date()
                inv["days_overdue"] = max(0, (date.today() - due).days)
                if inv["days_overdue"] > 0 and inv.get("status") == "unpaid":
                    inv["status"] = "overdue"

        return {
            "ok": True,
            "count": len(result.data or []),
            "data": result.data or [],
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to list invoices: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/{invoice_id}")
async def get_invoice(invoice_id: str) -> dict:
    """Get invoice detail."""
    try:
        sb = get_supabase()

        result = (
            sb.table("invoices")
            .select("*")
            .eq("id", invoice_id)
            .maybe_single()
            .execute()
        )

        if not result.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")

        inv = result.data

        # Calculate days overdue
        inv["days_overdue"] = 0
        if inv.get("status") in ("unpaid", "overdue") and inv.get("due_date"):
            due = datetime.fromisoformat(inv["due_date"]).date()
            inv["days_overdue"] = max(0, (date.today() - due).days)

        # Fetch carrier info
        if inv.get("carrier_id"):
            carrier_res = (
                sb.table("active_carriers")
                .select("company_name, dot_number, email")
                .eq("id", inv["carrier_id"])
                .maybe_single()
                .execute()
            )
            inv["carrier"] = carrier_res.data

        # Fetch load info if linked
        if inv.get("load_id"):
            load_res = (
                sb.table("loads")
                .select("load_number, broker_name, origin_city, dest_city")
                .eq("id", inv["load_id"])
                .maybe_single()
                .execute()
            )
            inv["load"] = load_res.data

        return {
            "ok": True,
            "data": inv,
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to get invoice: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.patch("/{invoice_id}")
async def update_invoice(invoice_id: str, payload: InvoiceUpdate) -> dict:
    """Update invoice status, amount, or payment info."""
    try:
        sb = get_supabase()

        # Check invoice exists
        existing = (
            sb.table("invoices")
            .select("id")
            .eq("id", invoice_id)
            .maybe_single()
            .execute()
        )

        if not existing.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "invoice not found")

        # Build update data
        update_data = {}
        if payload.status:
            update_data["status"] = payload.status
            if payload.status == "paid":
                update_data["paid_at"] = datetime.now(timezone.utc).isoformat()
        if payload.amount is not None:
            update_data["amount"] = payload.amount
        if payload.due_date:
            update_data["due_date"] = payload.due_date.isoformat()
        if payload.paid_at:
            update_data["paid_at"] = payload.paid_at
        if payload.payment_method:
            update_data["payment_method"] = payload.payment_method
        if payload.notes:
            update_data["notes"] = payload.notes

        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        result = (
            sb.table("invoices")
            .update(update_data)
            .eq("id", invoice_id)
            .execute()
        )

        return {
            "ok": True,
            "invoice": result.data[0] if result.data else None,
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to update invoice: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/stats/summary")
async def invoice_summary() -> dict:
    """Get invoice summary stats (total, by status, aging)."""
    try:
        sb = get_supabase()

        all_invoices = sb.table("invoices").select("*").execute()
        invoices = all_invoices.data or []

        # Calculate metrics
        total_amount = sum(float(i.get("amount", 0)) for i in invoices)
        paid = [i for i in invoices if i.get("status") == "paid"]
        unpaid = [i for i in invoices if i.get("status") in ("unpaid", "overdue")]

        paid_amount = sum(float(i.get("amount", 0)) for i in paid)
        unpaid_amount = sum(float(i.get("amount", 0)) for i in unpaid)

        # Age unpaid invoices
        aged = {"0-7d": 0, "8-14d": 0, "15-30d": 0, "30+d": 0}
        for inv in unpaid:
            if inv.get("due_date"):
                due = datetime.fromisoformat(inv["due_date"]).date()
                days = (date.today() - due).days
                if days < 0:
                    aged["0-7d"] += float(inv.get("amount", 0))
                elif days <= 7:
                    aged["0-7d"] += float(inv.get("amount", 0))
                elif days <= 14:
                    aged["8-14d"] += float(inv.get("amount", 0))
                elif days <= 30:
                    aged["15-30d"] += float(inv.get("amount", 0))
                else:
                    aged["30+d"] += float(inv.get("amount", 0))

        return {
            "ok": True,
            "data": {
                "total_invoices": len(invoices),
                "total_amount": total_amount,
                "paid_invoices": len(paid),
                "paid_amount": paid_amount,
                "unpaid_invoices": len(unpaid),
                "unpaid_amount": unpaid_amount,
                "aged_unpaid": aged,
            },
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to get invoice summary: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

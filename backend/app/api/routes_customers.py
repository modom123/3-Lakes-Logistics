"""Customer / Shipper CRM — CRUD + load history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..logging_service import get_logger
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("route.customers")
router = APIRouter(dependencies=[Depends(require_bearer)])


class CustomerIn(BaseModel):
    company_name:  str
    contact_name:  str | None = None
    email:         str | None = None
    phone:         str | None = None
    address:       str | None = None
    city:          str | None = None
    state:         str | None = None
    zip:           str | None = None
    customer_type: str = "broker"       # shipper | broker | both
    payment_terms: str = "net30"        # net15 | net30 | net45 | quick_pay
    credit_limit:  float | None = None
    credit_rating: str | None = None    # A | B | C | D
    mc_number:     str | None = None
    dot_number:    str | None = None
    notes:         str | None = None
    status:        str = "active"


@router.get("/customers")
def list_customers(
    search: str | None = None,
    customer_type: str | None = None,
    status: str = "active",
    limit: int = 200,
) -> dict:
    sb = get_supabase()
    q = sb.table("customers").select("*").order("company_name").limit(limit)
    if status and status != "all":
        q = q.eq("status", status)
    if customer_type:
        q = q.eq("customer_type", customer_type)
    if search:
        q = q.ilike("company_name", f"%{search}%")
    res = q.execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.post("/customers")
def create_customer(body: CustomerIn) -> dict:
    sb = get_supabase()
    # Check for duplicate
    existing = sb.table("customers").select("id").eq("company_name", body.company_name).execute()
    if existing.data:
        raise HTTPException(409, f"Customer '{body.company_name}' already exists")
    payload = body.model_dump(exclude_none=True)
    res = sb.table("customers").insert(payload).execute()
    return {"ok": True, "item": res.data[0] if res.data else {}}


@router.get("/customers/{customer_id}")
def get_customer(customer_id: str) -> dict:
    sb = get_supabase()
    c = sb.table("customers").select("*").eq("id", customer_id).maybe_single().execute()
    if not c.data:
        raise HTTPException(404, "customer not found")
    # Load history
    loads = (
        sb.table("loads")
        .select("id,load_number,origin,destination,rate_total,rate,status,pickup_date,created_at,driver_name")
        .eq("customer_id", customer_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"ok": True, "customer": c.data, "loads": loads.data or []}


@router.patch("/customers/{customer_id}")
def update_customer(customer_id: str, body: dict) -> dict:
    body.pop("id", None)
    get_supabase().table("customers").update(body).eq("id", customer_id).execute()
    return {"ok": True}


@router.delete("/customers/{customer_id}")
def deactivate_customer(customer_id: str) -> dict:
    get_supabase().table("customers").update({"status": "inactive"}).eq("id", customer_id).execute()
    return {"ok": True}


@router.post("/customers/find-or-create")
def find_or_create_customer(body: dict) -> dict:
    """Used by the execution engine: look up by company name, create if new."""
    company = (body.get("company_name") or "").strip()
    if not company:
        raise HTTPException(400, "company_name required")
    sb = get_supabase()
    existing = sb.table("customers").select("id,company_name").ilike("company_name", company).limit(1).execute()
    if existing.data:
        return {"ok": True, "customer_id": existing.data[0]["id"], "created": False}
    payload = {
        "company_name":  company,
        "email":         body.get("email"),
        "phone":         body.get("phone"),
        "customer_type": body.get("customer_type", "broker"),
    }
    res = sb.table("customers").insert({k: v for k, v in payload.items() if v is not None}).execute()
    cid = res.data[0]["id"] if res.data else None
    return {"ok": True, "customer_id": cid, "created": True}

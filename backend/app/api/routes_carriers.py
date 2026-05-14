"""Carriers CRUD — powers the EAGLE EYE `Carriers` page."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.get("/")
def list_carriers(
    status_filter: str | None = Query(default=None, alias="status"),
    plan: str | None = None,
    limit: int = 200,
) -> dict:
    q = get_supabase().table("active_carriers").select("*").order("created_at", desc=True).limit(limit)
    if status_filter:
        q = q.eq("status", status_filter)
    if plan:
        q = q.eq("plan", plan)
    res = q.execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.get("/{carrier_id}")
def get_carrier(carrier_id: str) -> dict:
    res = get_supabase().table("active_carriers").select("*").eq("id", carrier_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "carrier not found")
    return res.data


@router.patch("/{carrier_id}/status")
def update_status(carrier_id: str, new_status: str) -> dict:
    if new_status not in {"onboarding", "onboarding_incomplete", "active", "suspended", "churned"}:
        raise HTTPException(400, "invalid status")
    get_supabase().table("active_carriers").update({"status": new_status}).eq("id", carrier_id).execute()
    return {"ok": True, "carrier_id": carrier_id, "status": new_status}


@router.patch("/{carrier_id}/complete-onboarding")
async def complete_onboarding(carrier_id: str, data: dict, bg: BackgroundTasks = BackgroundTasks()) -> dict:
    """Accept remaining fields to complete a partial onboarding.

    Accepts any subset of: ein, dot_number, mc_number, insurance_carrier,
    policy_number, bank_routing, bank_account, account_type, payee_name, email
    """
    from ..agents import penny, shield
    from ..triggers import fire_onboarding
    from ..logging_service import log_agent

    sb = get_supabase()

    result = sb.table("active_carriers").select("*").eq("id", carrier_id).execute()
    if not result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "carrier not found")
    carrier = result.data[0]

    # Update allowed carrier fields
    allowed = ["ein", "dot_number", "mc_number", "email", "phone",
               "address", "insurance_carrier", "policy_number"]
    update = {k: v for k, v in data.items() if k in allowed and v}

    # Upsert banking if provided
    banking = {}
    if data.get("bank_routing"):
        r = data["bank_routing"]
        banking["bank_routing_last4"] = r[-4:] if len(r) >= 4 else r
    if data.get("bank_account"):
        a = data["bank_account"]
        banking["bank_account_last4"] = a[-4:] if len(a) >= 4 else a
    if data.get("account_type"):
        banking["account_type"] = data["account_type"]
    if data.get("payee_name"):
        banking["payee_name"] = data["payee_name"]

    if banking:
        existing = sb.table("banking_accounts").select("id").eq("carrier_id", carrier_id).execute()
        if existing.data:
            sb.table("banking_accounts").update(banking).eq("carrier_id", carrier_id).execute()
        else:
            sb.table("banking_accounts").insert({"carrier_id": carrier_id, **banking}).execute()

    # Check which fields are still missing
    merged = {**carrier, **update}
    still_missing = [f for f in ["ein", "dot_number", "mc_number", "insurance_carrier"] if not merged.get(f)]
    has_banking = bool(banking) or bool(
        sb.table("banking_accounts").select("id").eq("carrier_id", carrier_id).execute().data
    )
    if not has_banking:
        still_missing.append("banking")

    if not still_missing:
        update["status"] = "onboarding"
        update["onboarding_missing_fields"] = None
    else:
        update["onboarding_missing_fields"] = still_missing

    if update:
        sb.table("active_carriers").update(update).eq("id", carrier_id).execute()

    # Trigger full pipeline if now complete
    if not still_missing and carrier.get("status") == "onboarding_incomplete":
        email = merged.get("email", "")
        plan = merged.get("plan", "founders")
        checkout_url = penny.create_checkout_session(carrier_id, plan, str(email), 1)
        shield.enqueue_safety_check(carrier_id, merged.get("dot_number"), merged.get("mc_number"))
        bg.add_task(fire_onboarding, carrier_id)
        if email:
            from ..api.routes_intake import _send_welcome_email
            bg.add_task(_send_welcome_email, email, merged.get("company_name", ""), carrier_id, [], plan)
        log_agent("atlas", "onboarding.completed", carrier_id=carrier_id)
        return {"ok": True, "status": "onboarding", "stripe_checkout_url": checkout_url}

    return {"ok": True, "status": "onboarding_incomplete", "still_missing": still_missing}

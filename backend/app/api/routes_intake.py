"""POST /api/carriers/intake — accepts the 6-step form payload from
index (7).html's oSub() and fans it out to every child table.

Steps executed on one submission:
  1. Insert into active_carriers            → carrier_id
  2. Insert into fleet_assets                 (Step 2 of form)
  3. Insert into eld_connections              (Step 3)
  4. Insert into insurance_compliance         (Step 4) — Shield runs async
  5. Insert into banking_accounts             (Step 5)
  6. Insert into signatures_audit             (Step 6 e-sign)
  7. Decrement founders_inventory.claimed+1   (countdown)
  8. Enqueue Shield safety-light check (agent_log row)
  9. Return Stripe checkout URL for Penny to confirm
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from ..agents import penny, shield
from ..logging_service import get_logger, log_agent
from ..models.intake import CarrierIntake, IntakeResponse
from ..supabase_client import get_supabase

log = get_logger("route.intake")
router = APIRouter()


def _last4(s: str | None) -> str | None:
    if not s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits[-4:] if len(digits) >= 4 else digits


@router.post("/intake", response_model=IntakeResponse, status_code=status.HTTP_201_CREATED)
async def carrier_intake(payload: CarrierIntake, request: Request) -> IntakeResponse:
    sb = get_supabase()
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    # Normalize alternates from the form
    phone = payload.phone or payload.owner_phone
    email = payload.email or payload.owner_email
    address = payload.address or ", ".join(filter(None, [
        payload.address_city, payload.address_state, payload.address_zip]))

    # 1. active_carriers
    carrier_row = {
        "company_name": payload.company_name,
        "legal_entity": payload.legal_entity,
        "dot_number": payload.dot_number,
        "mc_number": payload.mc_number,
        "ein": payload.ein,
        "phone": phone,
        "email": email,
        "address": address or None,
        "years_in_business": payload.years_in_business,
        "plan": payload.plan,
        "esign_name": payload.esign_name,
        "esign_ip": payload.esign_ip or ip,
        "esign_user_agent": payload.esign_user_agent or ua,
        "agreement_pdf_hash": payload.agreement_pdf_hash,
        "esign_timestamp": "now()",
        "status": "onboarding",
    }
    res = sb.table("active_carriers").insert(carrier_row).execute()
    if not res.data:
        raise HTTPException(500, "carrier insert failed")
    carrier_id = res.data[0]["id"]

    # 2. fleet_assets (first truck)
    sb.table("fleet_assets").insert({
        "carrier_id": carrier_id,
        "truck_id": payload.truck_id,
        "vin": payload.vin,
        "year": payload.year,
        "make": payload.make,
        "model": payload.model,
        "trailer_type": payload.trailer_type,
        "max_weight_lbs": payload.max_weight,
        "equipment_count": payload.equipment_count,
    }).execute()

    # 3. eld_connections (token will be encrypted in production)
    if payload.eld_provider and payload.eld_provider != "other":
        sb.table("eld_connections").insert({
            "carrier_id": carrier_id,
            "eld_provider": payload.eld_provider,
            "eld_api_token": payload.eld_api_token,
            "eld_account_id": payload.eld_account_id,
            "status": "pending",
        }).execute()

    # 4. insurance_compliance (Shield kicks off a safety-light check)
    sb.table("insurance_compliance").insert({
        "carrier_id": carrier_id,
        "insurance_carrier": payload.insurance_carrier,
        "policy_number": payload.policy_number,
        "policy_expiry": payload.policy_expiry,
        "bmc91_ack": payload.bmc91_ack,
        "mcs90_ack": payload.mcs90_ack,
        "safer_consent": payload.safer_consent,
        "csa_consent": payload.csa_consent,
        "clearinghouse_consent": payload.clearinghouse_consent,
        "psp_consent": payload.psp_consent,
    }).execute()

    # 5. banking_accounts (only last4; token provisioned via Stripe/Plaid later)
    sb.table("banking_accounts").insert({
        "carrier_id": carrier_id,
        "bank_routing_last4": _last4(payload.bank_routing),
        "bank_account_last4": _last4(payload.bank_account),
        "account_type": payload.account_type,
        "payee_name": payload.payee_name,
    }).execute()

    # 6. signatures_audit
    sb.table("signatures_audit").insert({
        "carrier_id": carrier_id,
        "doc_type": "dispatch_agreement",
        "esign_name": payload.esign_name,
        "ip": payload.esign_ip or ip,
        "user_agent": payload.esign_user_agent or ua,
        "pdf_hash": payload.agreement_pdf_hash,
    }).execute()

    # 7. founders_inventory claim++
    sb.rpc("claim_founders_slot", {"p_category": payload.trailer_type}).execute() \
        if False else _inc_founders_claimed(sb, payload.trailer_type)

    # 8. Kick Shield + Penny
    log_agent("atlas", "intake_received", carrier_id=carrier_id, payload={"plan": payload.plan})
    checkout_url = penny.create_checkout_session(carrier_id, payload.plan, str(payload.email))
    shield.enqueue_safety_check(carrier_id, payload.dot_number, payload.mc_number)

    return IntakeResponse(
        ok=True,
        carrier_id=carrier_id,
        stripe_checkout_url=checkout_url,
        next_step="stripe_checkout",
    )


def _inc_founders_claimed(sb, category: str) -> None:
    row = sb.table("founders_inventory").select("claimed,total").eq("category", category).execute()
    if not row.data:
        return
    new_claimed = min(row.data[0]["claimed"] + 1, row.data[0]["total"])
    sb.table("founders_inventory").update({"claimed": new_claimed}).eq("category", category).execute()

"""POST /api/carriers/intake — accepts the 6-step form payload.

Supports partial submissions — missing EIN, DOT, banking, or insurance
sets status to 'onboarding_incomplete' and sends a welcome email with
a secure link to complete the profile. Full submissions run the entire pipeline.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from ..agents import penny, shield
from ..logging_service import get_logger, log_agent
from ..models.intake import CarrierIntake, IntakeResponse
from ..supabase_client import get_supabase
from ..triggers import fire_onboarding

log = get_logger("route.intake")
router = APIRouter()


def _last4(s: str | None) -> str | None:
    if not s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits[-4:] if len(digits) >= 4 else digits


def _missing_fields(payload: CarrierIntake, email: str | None) -> list[str]:
    missing = []
    if not payload.ein:
        missing.append("EIN / Tax ID")
    if not payload.dot_number:
        missing.append("USDOT Number")
    if not payload.mc_number:
        missing.append("MC Number")
    if not payload.insurance_carrier:
        missing.append("Insurance Carrier")
    if not payload.bank_routing:
        missing.append("Bank Routing Number")
    if not payload.bank_account:
        missing.append("Bank Account Number")
    return missing


async def _send_welcome_email(email: str, company_name: str, carrier_id: str, missing: list[str]) -> None:
    try:
        import httpx
        from ..settings import get_settings
        s = get_settings()
        if not s.postmark_server_token:
            return

        completion_url = f"https://3lakeslogistics.com/complete-onboarding?carrier_id={carrier_id}"
        missing_html = "".join(f"<li>{f}</li>" for f in missing)

        incomplete_block = f"""
        <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:20px;margin:20px 0;">
          <h3 style="color:#c2410c;margin-top:0;">⚠️ Complete Your Profile</h3>
          <p style="color:#334155;">To activate dispatch and payouts, please provide:</p>
          <ul style="color:#334155;line-height:1.8;">{missing_html}</ul>
          <a href="{completion_url}" style="display:inline-block;background:#C8902A;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;margin-top:12px;">Complete My Profile →</a>
        </div>""" if missing else """
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:20px;margin:20px 0;">
          <h3 style="color:#16a34a;margin-top:0;">✅ Profile Complete!</h3>
          <p style="color:#334155;">All information received. Your account is being fully activated.</p>
        </div>"""

        body_html = f"""<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
<div style="background:#0B2545;padding:20px;border-radius:8px 8px 0 0;text-align:center;">
  <h1 style="color:#C8902A;margin:0;">Welcome to 3 Lakes Logistics</h1>
  <p style="color:#94a3b8;margin:8px 0 0;">Founders Program</p>
</div>
<div style="background:#f8fafc;padding:30px;border-radius:0 0 8px 8px;">
  <h2 style="color:#0B2545;">You're In, {company_name}!</h2>
  <p>Your application has been received. Our dispatch team will have you booking loads within 24 hours.</p>
  <div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
    <h3 style="color:#0B2545;margin-top:0;">Founders Program Benefits</h3>
    <ul style="color:#334155;line-height:1.8;">
      <li>✅ 100% of every load rate — you keep it all</li>
      <li>✅ AI dispatch across 15+ load boards</li>
      <li>✅ 200-step automation (compliance, safety, payouts)</li>
      <li>✅ $300/month locked for life</li>
    </ul>
  </div>
  {incomplete_block}
  <p>Questions? <strong>(555) 000-1234</strong> · <a href="mailto:dispatch@3lakeslogistics.com">dispatch@3lakeslogistics.com</a></p>
  <p style="color:#94a3b8;font-size:12px;margin-top:24px;">Carrier ID: {carrier_id}</p>
</div></body></html>"""

        subject = f"Welcome to 3 Lakes Logistics — {'Complete Your Profile' if missing else 'You Are All Set!'}"
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                "https://api.postmarkapp.com/email",
                headers={"X-Postmark-Server-Token": s.postmark_server_token, "Content-Type": "application/json"},
                json={
                    "From": s.postmark_from_email, "To": email,
                    "Subject": subject, "HtmlBody": body_html,
                    "TextBody": f"Welcome {company_name}! {'Complete your profile: ' + completion_url if missing else 'All set — activating within 24 hours.'}",
                    "MessageStream": "outbound", "Tag": "carrier-welcome",
                },
            )
        log.info(f"Welcome email sent to {email}")
    except Exception as e:  # noqa: BLE001
        log.error(f"Welcome email failed: {e}")


@router.post("/intake", response_model=IntakeResponse, status_code=status.HTTP_201_CREATED)
async def carrier_intake(payload: CarrierIntake, request: Request,
                         bg: BackgroundTasks = BackgroundTasks()) -> IntakeResponse:
    sb = get_supabase()
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    # Normalize alternates from the form
    phone = payload.phone or payload.owner_phone
    email = payload.email or payload.owner_email
    address = payload.address or ", ".join(filter(None, [
        payload.address_city, payload.address_state, payload.address_zip]))

    # Detect missing fields — partial submissions get onboarding_incomplete status
    missing = _missing_fields(payload, email)
    onboarding_status = "onboarding_incomplete" if missing else "onboarding"

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
        "status": onboarding_status,
        "onboarding_missing_fields": missing or None,
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

    # 5. banking_accounts — only insert if at least one field provided
    if payload.bank_routing or payload.bank_account or payload.payee_name:
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

    # 8. Send welcome email (always — includes completion link if fields missing)
    if email:
        bg.add_task(_send_welcome_email, email, payload.company_name, carrier_id, missing)

    log_agent("atlas", "intake_received", carrier_id=carrier_id,
              payload={"plan": payload.plan, "status": onboarding_status, "missing": missing})

    # 9. Only run full pipeline if all required fields provided
    checkout_url = None
    if not missing:
        checkout_url = penny.create_checkout_session(carrier_id, payload.plan, str(email), payload.founders_truck_count)
        shield.enqueue_safety_check(carrier_id, payload.dot_number, payload.mc_number)
        bg.add_task(fire_onboarding, carrier_id)
        log_agent("atlas", "trigger.onboarding", carrier_id=carrier_id, result="queued")
    else:
        log.info(f"Partial intake {carrier_id} — missing: {missing}")

    return IntakeResponse(
        ok=True,
        carrier_id=carrier_id,
        stripe_checkout_url=checkout_url,
        next_step="complete_profile" if missing else "stripe_checkout",
    )


def _inc_founders_claimed(sb, category: str) -> None:
    row = sb.table("founders_inventory").select("claimed,total").eq("category", category).execute()
    if not row.data:
        return
    new_claimed = min(row.data[0]["claimed"] + 1, row.data[0]["total"])
    sb.table("founders_inventory").update({"claimed": new_claimed}).eq("category", category).execute()

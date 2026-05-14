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
        <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:20px;margin:30px 0;">
          <h3 style="color:#c2410c;margin-top:0;">📋 One More Step: Complete Your Profile</h3>
          <p style="color:#334155;margin-bottom:15px;">To activate dispatch and begin booking loads, please provide the following information:</p>
          <ul style="color:#334155;line-height:1.8;margin:10px 0;padding-left:20px;">{missing_html}</ul>
          <p style="color:#334155;font-size:14px;margin-top:15px;"><strong>Why we need this:</strong> These details ensure compliance with FMCSA regulations, enable direct payouts to your account, and activate your insurance compliance dashboard.</p>
          <a href="{completion_url}" style="display:inline-block;background:#C8902A;color:#fff;padding:14px 28px;border-radius:6px;text-decoration:none;font-weight:bold;margin-top:15px;font-size:16px;">Complete My Profile →</a>
          <p style="color:#64748b;font-size:13px;margin-top:15px;">Takes 5–10 minutes • All fields required for dispatch activation</p>
        </div>""" if missing else """
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:20px;margin:30px 0;">
          <h3 style="color:#16a34a;margin-top:0;">✅ You're All Set!</h3>
          <p style="color:#334155;">All information received. Our dispatch team is activating your account now — you'll be booking loads within 24 hours.</p>
        </div>"""

        founders_details = """
        <div style="background:#FEF3C7;border-left:4px solid #F59E0B;padding:15px;margin:20px 0;border-radius:4px;">
          <p style="color:#333;margin:0;font-size:14px;"><strong>🚀 What You Get in the Founders Program:</strong></p>
          <p style="color:#555;margin:8px 0 0;font-size:13px;line-height:1.7;">You've been selected for our exclusive Founders Program. This is a lifetime commitment: you pay <strong>$300/month</strong> (locked forever) and you keep <strong>100% of every load rate</strong> you book. No hidden fees. No volume minimums. No long-term contracts (except the Founders lock-in). This offer never increases — even if we raise prices for new carriers, your rate stays $300/month.</p>
        </div>
        """

        subscription_details = """
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
          <h3 style="color:#0B2545;margin-top:0;margin-bottom:15px;">💳 How Your Subscription Works</h3>
          <div style="color:#334155;font-size:14px;line-height:1.8;">
            <p><strong>Pricing:</strong> $300/month (billed on the same date each month)</p>
            <p><strong>What's included:</strong></p>
            <ul style="margin:10px 0;padding-left:20px;">
              <li>AI dispatch across 15+ load boards (DAT, Truckstop, 123Loadboard, Loadsmart, JB Hunt, etc.)</li>
              <li>Automated rate negotiation and booking</li>
              <li>200+ compliance & safety automations (FMCSA safety checks, insurance verification, CSA monitoring, driver CDL tracking, medical card alerts)</li>
              <li>Direct payouts to your bank account (after load completion)</li>
              <li>Real-time load tracking and proof-of-delivery verification</li>
              <li>Founder priority support (phone, email, Slack)</li>
            </ul>
            <p><strong>When does billing start?</strong> On the date your profile is fully activated (once all required info is submitted). Your first charge will be prorated if we activate mid-month.</p>
            <p><strong>Can you cancel?</strong> Yes — you can cancel anytime with 30 days' notice. No penalties, no surprise fees. But the Founders lock-in ($300/month forever) is only available if you stay with us.</p>
            <p><strong>What if you grow?</strong> As you book more loads, you keep 100% of the rate — there's no ceiling or cap. Some Founders carriers book 10–15 loads per week at an average of $2,200/load. The math works in your favor.</p>
          </div>
        </div>
        """

        support_details = """
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
          <h3 style="color:#0B2545;margin-top:0;margin-bottom:15px;">🎯 What Happens Next</h3>
          <div style="color:#334155;font-size:14px;line-height:1.8;">
            <p><strong>Today:</strong> You've been enrolled in the Founders Program. Our ops team is reviewing your application.</p>
            <p><strong>Within 24 hours:</strong> You'll receive activation confirmation + your carrier dashboard login.</p>
            <p><strong>Within 48 hours:</strong> First loads will appear in your dispatch board. Vance (our AI dispatch agent) will start sending you pre-negotiated load offers.</p>
            <p><strong>Day 7:</strong> You'll have completed your first loads and will have received your first payout.</p>
          </div>
        </div>
        """

        contact_block = """
        <div style="background:#f8fafc;border-top:2px solid #C8902A;padding:20px;margin:20px 0;text-align:center;">
          <p style="color:#0B2545;font-size:14px;margin:0 0 12px;"><strong>Questions? We're Here to Help</strong></p>
          <p style="color:#334155;font-size:13px;margin:8px 0;">
            <strong>📞 Dispatch Team:</strong> (555) 000-1234<br>
            <strong>✉️ Email:</strong> <a href="mailto:dispatch@3lakeslogistics.com" style="color:#C8902A;text-decoration:none;">dispatch@3lakeslogistics.com</a><br>
            <strong>💬 Slack:</strong> Founders-only channel (access after activation)
          </p>
        </div>
        """

        body_html = f"""<html><body style="font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;max-width:650px;margin:0 auto;padding:0;background:#f5f5f5;">
<div style="background:#0B2545;padding:30px 20px;text-align:center;border-bottom:4px solid #C8902A;">
  <h1 style="color:#C8902A;margin:0;font-size:28px;font-weight:700;">Welcome to 3 Lakes Logistics</h1>
  <p style="color:#C8902A;margin:8px 0 0;font-size:14px;letter-spacing:1px;text-transform:uppercase;font-weight:600;">FOUNDERS PROGRAM</p>
</div>

<div style="background:#fff;padding:30px 30px;margin:20px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
  <h2 style="color:#0B2545;margin-top:0;margin-bottom:10px;font-size:22px;">You're In, {company_name}!</h2>
  <p style="color:#555;font-size:15px;line-height:1.7;margin-bottom:20px;">Your application has been received and reviewed. Welcome to an elite group of carrier partners who've locked in lifetime rates with 3 Lakes Logistics.</p>

  {founders_details}

  {incomplete_block if missing else '<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:20px;margin:30px 0;"><h3 style="color:#16a34a;margin-top:0;">✅ All Set!</h3><p style="color:#334155;">Your profile is complete. Our dispatch team is activating your account now — you\'ll be booking loads within 24 hours.</div>'}

  {subscription_details}

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
    <h3 style="color:#0B2545;margin-top:0;margin-bottom:15px;">🔑 Founders Program Benefits (Lock-In Terms)</h3>
    <div style="color:#334155;font-size:14px;line-height:1.9;">
      <p><strong>✅ 100% of Load Rates</strong> — You negotiate the rate with brokers, and you keep every dollar. No percentage cuts, no hidden deductions.</p>
      <p><strong>✅ $300/Month Locked for Life</strong> — Your subscription price never increases, even if we raise rates for new carriers.</p>
      <p><strong>✅ Zero Setup Fees</strong> — No onboarding cost, no hidden charges. You only pay the monthly subscription.</p>
      <p><strong>✅ No Long-Term Contract</strong> — You can cancel with 30 days' notice (except the Founders program itself, which is locked at $300/month if you stay with us).</p>
      <p><strong>✅ 200+ Automations</strong> — Compliance checks, safety audits, driver monitoring, payout processing, all running in the background.</p>
      <p><strong>✅ 15+ Load Boards</strong> — Access to DAT, Truckstop, 123Loadboard, Loadsmart, and more through our AI dispatcher.</p>
    </div>
  </div>

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
    <h3 style="color:#0B2545;margin-top:0;margin-bottom:15px;">💡 Why This Offer Is Special</h3>
    <div style="color:#334155;font-size:14px;line-height:1.9;">
      <p>We're not taking a cut of your load revenue. We make money through the $300/month subscription and by helping you book more loads, faster, with less operational overhead. This alignment means we're motivated to help you succeed.</p>
      <p>The Founders Program is a limited-time offer for early adopters. Once we close it, we won't open it again — new carriers pay higher subscription fees. You've secured your spot.</p>
    </div>
  </div>

  {support_details}

  {contact_block}

  <p style="color:#94a3b8;font-size:11px;margin-top:30px;margin-bottom:0;text-align:center;">Carrier ID: <strong>{carrier_id}</strong></p>
</div>

</body></html>"""

        subject = f"Welcome to 3 Lakes Logistics Founders Program — {'Complete Your Profile' if missing else 'You\'re All Set!'}"
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                "https://api.postmarkapp.com/email",
                headers={"X-Postmark-Server-Token": s.postmark_server_token, "Content-Type": "application/json"},
                json={
                    "From": s.postmark_from_email, "To": email,
                    "Subject": subject, "HtmlBody": body_html,
                    "TextBody": f"Welcome {company_name}! {'Complete your profile: ' + completion_url if missing else 'All set — activating within 24 hours.'}\n\nYou've been accepted into the Founders Program. Keep 100% of every load rate. $300/month, locked for life.\n\nQuestions? dispatch@3lakeslogistics.com or (555) 000-1234",
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

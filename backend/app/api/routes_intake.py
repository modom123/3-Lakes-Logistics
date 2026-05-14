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


_CONTACT_BLOCK = """
<div style="border-top:2px solid #C8902A;padding:20px;margin-top:30px;text-align:center;">
  <p style="color:#0B2545;font-size:14px;margin:0 0 10px;"><strong>Questions? We're Here.</strong></p>
  <p style="color:#334155;font-size:13px;margin:0;line-height:2;">
    <strong>📞 Dispatch:</strong> (555) 000-1234<br>
    <strong>✉️ Email:</strong> <a href="mailto:dispatch@3lakeslogistics.com" style="color:#C8902A;text-decoration:none;">dispatch@3lakeslogistics.com</a>
  </p>
</div>"""

_WHAT_HAPPENS_NEXT = """
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
  <h3 style="color:#0B2545;margin-top:0;">🎯 What Happens Next</h3>
  <div style="color:#334155;font-size:14px;line-height:1.9;">
    <p><strong>Today</strong> — Our ops team reviews your application.</p>
    <p><strong>Within 24 hrs</strong> — Activation confirmation + carrier dashboard access.</p>
    <p><strong>Within 48 hrs</strong> — Vance (our AI dispatch agent) starts sending pre-negotiated load offers.</p>
    <p><strong>Day 7</strong> — First loads completed, first payout deposited.</p>
  </div>
</div>"""


def _html_incomplete_block(missing: list[str], completion_url: str) -> str:
    missing_html = "".join(f"<li style='margin-bottom:6px;'>{f}</li>" for f in missing)
    return f"""
<div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:20px;margin:25px 0;">
  <h3 style="color:#c2410c;margin-top:0;">📋 One More Step: Complete Your Profile</h3>
  <p style="color:#334155;font-size:14px;">To activate dispatch and begin booking loads, please provide:</p>
  <ul style="color:#334155;line-height:1.8;padding-left:20px;">{missing_html}</ul>
  <p style="color:#334155;font-size:13px;margin-top:12px;"><strong>Why we need this:</strong> These details ensure FMCSA compliance, enable direct payouts, and activate your safety dashboard.</p>
  <a href="{completion_url}" style="display:inline-block;background:#C8902A;color:#fff;padding:13px 26px;border-radius:6px;text-decoration:none;font-weight:bold;margin-top:14px;font-size:15px;">Complete My Profile →</a>
  <p style="color:#64748b;font-size:12px;margin-top:12px;">Takes 5–10 minutes · All fields are required for dispatch activation</p>
</div>"""


def _html_complete_block() -> str:
    return """
<div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:20px;margin:25px 0;">
  <h3 style="color:#16a34a;margin-top:0;">✅ Profile Complete — You're Activated!</h3>
  <p style="color:#334155;font-size:14px;">All information received. Our dispatch team is activating your account now.</p>
</div>"""


def _html_founders_email(company_name: str, carrier_id: str, missing: list[str], completion_url: str) -> str:
    status_block = _html_incomplete_block(missing, completion_url) if missing else _html_complete_block()
    next_block = "" if missing else _WHAT_HAPPENS_NEXT
    subject_tag = "FOUNDERS PROGRAM"
    badge_color = "#C8902A"

    return f"""<html><body style="font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;max-width:650px;margin:0 auto;background:#f5f5f5;">
<div style="background:#0B2545;padding:28px 20px;text-align:center;border-bottom:4px solid {badge_color};">
  <h1 style="color:{badge_color};margin:0;font-size:26px;font-weight:700;">Welcome to 3 Lakes Logistics</h1>
  <p style="color:{badge_color};margin:8px 0 0;font-size:13px;letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">{subject_tag}</p>
</div>
<div style="background:#fff;padding:28px 30px;margin:20px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">

  <h2 style="color:#0B2545;margin-top:0;">You're In, {company_name}!</h2>
  <p style="color:#555;font-size:15px;line-height:1.7;">Your application has been received. Welcome to our exclusive Founders Program — a lifetime commitment that puts you ahead of every future carrier we onboard.</p>

  <div style="background:#FEF3C7;border-left:4px solid #F59E0B;padding:15px;margin:20px 0;border-radius:4px;">
    <p style="color:#333;margin:0;font-size:14px;font-weight:600;">Founders Program — $300/Month, Locked for Life</p>
    <p style="color:#555;margin:8px 0 0;font-size:13px;line-height:1.7;">You pay a flat $300/month and keep <strong>100% of every load rate</strong> you book. No percentage cuts. No volume minimums. Even as we raise prices for new carriers, your rate stays $300/month — forever.</p>
  </div>

  {status_block}

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
    <h3 style="color:#0B2545;margin-top:0;">💳 How Your Subscription Works</h3>
    <div style="color:#334155;font-size:14px;line-height:1.9;">
      <p><strong>Price:</strong> $300/month, billed on the same date each month</p>
      <p><strong>Billing starts:</strong> On the date your profile is fully activated. First charge is prorated if activated mid-month.</p>
      <p><strong>What's included:</strong></p>
      <ul style="margin:8px 0;padding-left:20px;">
        <li>AI dispatch across 15+ load boards (DAT, Truckstop, 123Loadboard, Loadsmart, JB Hunt, and more)</li>
        <li>Automated rate negotiation and load booking</li>
        <li>200+ compliance and safety automations — FMCSA checks, CSA monitoring, CDL expiry alerts, medical card tracking</li>
        <li>Direct payouts — 100% of load rate deposited after delivery confirmation</li>
        <li>Real-time load tracking and proof-of-delivery management</li>
        <li>Priority Founders support (phone, email)</li>
      </ul>
      <p><strong>Can you cancel?</strong> Yes — 30 days' notice, no penalties, no surprise fees. The Founders lock-in price ($300/month) is only maintained if you remain active.</p>
      <p><strong>Growth potential:</strong> Some Founders carriers book 10–15 loads per week at $2,200+ per load. You keep every dollar of every rate — your income scales with the loads you accept.</p>
    </div>
  </div>

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
    <h3 style="color:#0B2545;margin-top:0;">🔑 Your Founders Benefits at a Glance</h3>
    <div style="color:#334155;font-size:14px;line-height:2;">
      <p>✅ <strong>100% of Load Rates</strong> — every dollar from the broker goes to you</p>
      <p>✅ <strong>$300/Month, Locked Forever</strong> — price never increases</p>
      <p>✅ <strong>Zero Setup or Onboarding Fees</strong></p>
      <p>✅ <strong>No Long-Term Contract</strong> — cancel with 30 days' notice</p>
      <p>✅ <strong>200+ Background Automations</strong> — compliance, safety, payouts run on autopilot</p>
      <p>✅ <strong>15+ Load Boards</strong> — AI dispatcher searches and negotiates across all of them</p>
      <p>✅ <strong>Priority Founders Support</strong> — direct line to the dispatch team</p>
    </div>
  </div>

  {next_block}

  {_CONTACT_BLOCK}
  <p style="color:#94a3b8;font-size:11px;margin-top:24px;text-align:center;">Carrier ID: {carrier_id}</p>
</div>
</body></html>"""


def _html_standard_email(company_name: str, carrier_id: str, missing: list[str], completion_url: str) -> str:
    status_block = _html_incomplete_block(missing, completion_url) if missing else _html_complete_block()
    next_block = "" if missing else _WHAT_HAPPENS_NEXT

    return f"""<html><body style="font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;max-width:650px;margin:0 auto;background:#f5f5f5;">
<div style="background:#0B2545;padding:28px 20px;text-align:center;border-bottom:4px solid #3B82F6;">
  <h1 style="color:#fff;margin:0;font-size:26px;font-weight:700;">Welcome to 3 Lakes Logistics</h1>
  <p style="color:#93C5FD;margin:8px 0 0;font-size:13px;letter-spacing:1.5px;text-transform:uppercase;font-weight:600;">STANDARD PLAN — 8% PER LOAD</p>
</div>
<div style="background:#fff;padding:28px 30px;margin:20px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">

  <h2 style="color:#0B2545;margin-top:0;">You're In, {company_name}!</h2>
  <p style="color:#555;font-size:15px;line-height:1.7;">Your application has been received. You're on our Standard Plan — full access to our AI dispatch platform with no monthly subscription fee. We earn when you earn.</p>

  <div style="background:#EFF6FF;border-left:4px solid #3B82F6;padding:15px;margin:20px 0;border-radius:4px;">
    <p style="color:#1E40AF;margin:0;font-size:14px;font-weight:600;">Standard Plan — No Monthly Fee, 8% Per Load</p>
    <p style="color:#334155;margin:8px 0 0;font-size:13px;line-height:1.7;">You pay <strong>$0/month</strong> upfront. When a load is delivered and payment confirmed, we deduct <strong>8% of the load rate</strong> and deposit the remaining <strong>92%</strong> directly to your bank account. No loads booked = no fees.</p>
  </div>

  {status_block}

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
    <h3 style="color:#0B2545;margin-top:0;">💳 How Your Plan Works</h3>
    <div style="color:#334155;font-size:14px;line-height:1.9;">
      <p><strong>Monthly fee:</strong> $0 — no subscription, no upfront cost</p>
      <p><strong>How we're paid:</strong> 8% of each load rate, deducted automatically at payout</p>
      <p><strong>Your take-home:</strong> 92% of every load rate, direct deposited after delivery confirmation</p>
      <p><strong>Payout timing:</strong> 3–5 business days after proof of delivery is confirmed</p>
      <p><strong>Example:</strong> A $2,000 load → 3 Lakes earns $160, you receive $1,840</p>
      <p><strong>What's included:</strong></p>
      <ul style="margin:8px 0;padding-left:20px;">
        <li>AI dispatch across 15+ load boards (DAT, Truckstop, 123Loadboard, Loadsmart, JB Hunt, and more)</li>
        <li>Automated rate negotiation and load booking</li>
        <li>200+ compliance and safety automations — FMCSA checks, CSA monitoring, CDL expiry alerts, medical card tracking</li>
        <li>Direct payouts — 92% of load rate deposited after delivery</li>
        <li>Real-time load tracking and proof-of-delivery management</li>
        <li>Standard carrier support (phone, email)</li>
      </ul>
      <p><strong>Can you cancel?</strong> Yes — 30 days' notice, anytime. No cancellation fees.</p>
      <p><strong>Upgrade to Founders?</strong> If spots become available, you can lock in the $300/month Founders rate and keep 100% of loads. Contact us to inquire.</p>
    </div>
  </div>

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px;margin:20px 0;">
    <h3 style="color:#0B2545;margin-top:0;">✅ Your Plan Benefits at a Glance</h3>
    <div style="color:#334155;font-size:14px;line-height:2;">
      <p>✅ <strong>$0/Month Subscription</strong> — no upfront cost, pay only when you earn</p>
      <p>✅ <strong>92% of Every Load Rate</strong> — deposited after delivery</p>
      <p>✅ <strong>Zero Setup or Onboarding Fees</strong></p>
      <p>✅ <strong>No Long-Term Contract</strong> — cancel with 30 days' notice</p>
      <p>✅ <strong>200+ Background Automations</strong> — compliance, safety, payouts run on autopilot</p>
      <p>✅ <strong>15+ Load Boards</strong> — AI dispatcher searches and negotiates across all of them</p>
    </div>
  </div>

  {next_block}

  {_CONTACT_BLOCK}
  <p style="color:#94a3b8;font-size:11px;margin-top:24px;text-align:center;">Carrier ID: {carrier_id}</p>
</div>
</body></html>"""


async def _send_welcome_email(email: str, company_name: str, carrier_id: str, missing: list[str], plan: str = "founders") -> None:
    try:
        import httpx
        from ..settings import get_settings
        s = get_settings()
        if not s.postmark_server_token:
            return

        completion_url = f"https://3lakeslogistics.com/complete-onboarding?carrier_id={carrier_id}"
        is_founders = plan in ("founders", "pro", "enterprise", "discuss")

        action = "Complete Your Profile" if missing else ("You're All Set!" if is_founders else "You're Activated!")
        if is_founders:
            body_html = _html_founders_email(company_name, carrier_id, missing, completion_url)
            subject = f"Welcome to 3 Lakes Logistics Founders Program — {action}"
            text_body = f"Welcome {company_name}! You're in the Founders Program ($300/month, keep 100% of loads). {'Complete your profile: ' + completion_url if missing else 'All set — activating now.'}\n\nQuestions? dispatch@3lakeslogistics.com"
        else:
            body_html = _html_standard_email(company_name, carrier_id, missing, completion_url)
            subject = f"Welcome to 3 Lakes Logistics — {action}"
            text_body = f"Welcome {company_name}! You're on the Standard Plan (8% per load, $0/month). {'Complete your profile: ' + completion_url if missing else 'All set — activating now.'}\n\nQuestions? dispatch@3lakeslogistics.com"

        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(
                "https://api.postmarkapp.com/email",
                headers={"X-Postmark-Server-Token": s.postmark_server_token, "Content-Type": "application/json"},
                json={
                    "From": s.postmark_from_email, "To": email,
                    "Subject": subject, "HtmlBody": body_html,
                    "TextBody": text_body,
                    "MessageStream": "outbound", "Tag": "carrier-welcome",
                },
            )
        log.info(f"Welcome email sent to {email} (plan={plan}, missing={len(missing)})")
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
        bg.add_task(_send_welcome_email, email, payload.company_name, carrier_id, missing, payload.plan)

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

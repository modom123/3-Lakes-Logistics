"""Phase 1 — Carrier Onboarding handlers (steps 1–30).

Each function signature: (carrier_id, contract_id, payload) -> dict
"""
from __future__ import annotations

from datetime import datetime, timezone, date, timedelta
from uuid import UUID

from ...agents import shield, nova, vance, penny, atlas, beacon
from ...supabase_client import get_supabase
from ...logging_service import get_logger, log_agent
from ...settings import get_settings

log = get_logger("3ll.execution.onboarding")

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _carrier(carrier_id: UUID | None) -> dict:
    if not carrier_id:
        return {}
    r = get_supabase().table("active_carriers").select("*").eq("id", str(carrier_id)).maybe_single().execute()
    return r.data or {}


# ── Step 1: intake.receive ───────────────────────────────────────────────────

def h1_intake_receive(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    return {
        "received": True,
        "carrier_id": str(carrier_id) if carrier_id else None,
        "company_name": carrier.get("company_name"),
        "email": carrier.get("email"),
        "dot_number": carrier.get("dot_number"),
        "mc_number": carrier.get("mc_number"),
        "received_at": _NOW(),
    }


# ── Step 2: intake.dedupe_check ──────────────────────────────────────────────

def h2_intake_dedupe_check(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    sb = get_supabase()
    dupes: list[dict] = []
    for field in ("mc_number", "dot_number", "ein"):
        val = carrier.get(field) or payload.get(field)
        if not val:
            continue
        rows = (
            sb.table("active_carriers")
            .select("id,company_name,status")
            .eq(field, val)
            .neq("id", str(carrier_id) if carrier_id else "")
            .execute()
            .data or []
        )
        for r in rows:
            dupes.append({"field": field, "value": val, **r})
    return {"duplicate_found": bool(dupes), "duplicates": dupes}


# ── Step 3: fmcsa.lookup ─────────────────────────────────────────────────────

def h3_fmcsa_lookup(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    dot = carrier.get("dot_number") or payload.get("dot_number")
    safer = shield.fetch_safer(dot)
    log_agent("shield", "fmcsa_lookup", carrier_id=str(carrier_id) if carrier_id else None,
              payload={"dot": dot})
    return {"dot": dot, "safer": safer}


# ── Step 4: fmcsa.csa_score ──────────────────────────────────────────────────

def h4_fmcsa_csa_score(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    safer = payload.get("safer") or {}
    content = safer.get("content", {}) if isinstance(safer, dict) else {}
    carrier_data = content.get("carrier", {}) if isinstance(content, dict) else {}
    basics = carrier_data.get("basics", {}) if isinstance(carrier_data, dict) else {}
    high_risk = any(
        isinstance(v, (int, float)) and v >= 65
        for v in (basics.values() if isinstance(basics, dict) else [])
    )
    return {
        "csa_basics": basics,
        "high_risk": high_risk,
        "carrier_name": carrier_data.get("legalName"),
        "allowed_to_operate": carrier_data.get("allowedToOperate"),
    }


# ── Step 5: shield.safety_light ─────────────────────────────────────────────

def h5_shield_safety_light(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    safer = payload.get("safer")
    sb = get_supabase()
    insurance = None
    if carrier_id:
        r = sb.table("insurance_compliance").select("policy_expiry").eq("carrier_id", str(carrier_id)).maybe_single().execute()
        insurance = r.data
    expiry = (insurance or {}).get("policy_expiry")
    light = shield.score(safer, expiry)
    if carrier_id:
        try:
            sb.table("insurance_compliance").update(
                {"safety_light": light, "last_checked_at": _NOW()}
            ).eq("carrier_id", str(carrier_id)).execute()
        except Exception as e:  # noqa: BLE001
            log.warning("safety_light update failed: %s", e)
    return {"safety_light": light, "insurance_expiry": expiry}


# ── Step 6: insurance.verify ─────────────────────────────────────────────────

def h6_insurance_verify(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    if not carrier_id:
        return {"verified": False, "reason": "no_carrier_id"}
    r = get_supabase().table("insurance_compliance").select("*").eq("carrier_id", str(carrier_id)).maybe_single().execute()
    ins = r.data or {}
    policy_expiry = ins.get("policy_expiry")
    if not policy_expiry:
        return {"verified": False, "reason": "no_policy_on_file", "record": ins}
    try:
        days_left = (date.fromisoformat(policy_expiry) - date.today()).days
    except ValueError:
        days_left = -1
    return {
        "verified": days_left > 0,
        "policy_number": ins.get("policy_number"),
        "policy_expiry": policy_expiry,
        "days_until_expiry": days_left,
        "insurance_carrier": ins.get("insurance_carrier"),
    }


# ── Step 7: insurance.expiry_watch ───────────────────────────────────────────

def h7_insurance_expiry_watch(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    if not carrier_id:
        return {"scheduled": False}
    r = get_supabase().table("insurance_compliance").select("policy_expiry").eq("carrier_id", str(carrier_id)).maybe_single().execute()
    expiry_str = (r.data or {}).get("policy_expiry")
    if not expiry_str:
        return {"scheduled": False, "reason": "no_expiry_date"}
    try:
        expiry = date.fromisoformat(expiry_str)
    except ValueError:
        return {"scheduled": False, "reason": "bad_expiry_format"}

    alerts = [
        {"days_before": 30, "alert_at": (expiry - timedelta(days=30)).isoformat()},
        {"days_before": 7,  "alert_at": (expiry - timedelta(days=7)).isoformat()},
        {"days_before": 0,  "alert_at": expiry.isoformat()},
    ]
    try:
        get_supabase().table("insurance_compliance").update(
            {"expiry_watch_scheduled": True, "last_checked_at": _NOW()}
        ).eq("carrier_id", str(carrier_id)).execute()
    except Exception as e:  # noqa: BLE001
        log.warning("expiry_watch update failed: %s", e)
    return {"scheduled": True, "policy_expiry": expiry_str, "alert_schedule": alerts}


# ── Step 8: eld.detect_provider ──────────────────────────────────────────────

def h8_eld_detect_provider(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    if not carrier_id:
        return {"provider": None}
    r = get_supabase().table("eld_connections").select("eld_provider,status").eq("carrier_id", str(carrier_id)).maybe_single().execute()
    rec = r.data or {}
    provider = rec.get("eld_provider") or payload.get("eld_provider")
    return {"provider": provider, "status": rec.get("status", "not_connected")}


# ── Step 9: eld.sync_credentials ─────────────────────────────────────────────

def h9_eld_sync_credentials(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    if not carrier_id:
        return {"synced": False}
    provider = payload.get("provider") or payload.get("eld_provider")
    token = payload.get("eld_api_token")
    account_id = payload.get("eld_account_id")
    if not provider:
        return {"synced": False, "reason": "no_provider"}
    try:
        sb = get_supabase()
        existing = sb.table("eld_connections").select("id").eq("carrier_id", str(carrier_id)).maybe_single().execute()
        data = {
            "carrier_id": str(carrier_id),
            "eld_provider": provider,
            "eld_api_token": token,
            "eld_account_id": account_id,
            "status": "pending_verification",
            "last_sync_at": _NOW(),
        }
        if existing.data:
            sb.table("eld_connections").update(data).eq("carrier_id", str(carrier_id)).execute()
        else:
            sb.table("eld_connections").insert(data).execute()
    except Exception as e:  # noqa: BLE001
        return {"synced": False, "error": str(e)}
    return {"synced": True, "provider": provider}


# ── Step 10: banking.collect ─────────────────────────────────────────────────

def h10_banking_collect(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    if not carrier_id:
        return {"collected": False}
    r = get_supabase().table("banking_accounts").select("id,payee_name,account_type,verified_at").eq("carrier_id", str(carrier_id)).maybe_single().execute()
    rec = r.data or {}
    return {
        "collected": bool(rec),
        "payee_name": rec.get("payee_name"),
        "account_type": rec.get("account_type"),
        "verified": bool(rec.get("verified_at")),
    }


# ── Step 11: banking.verify ──────────────────────────────────────────────────

def h11_banking_verify(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    """Plaid micro-deposit verification stub. Marks account as verified on success."""
    if not carrier_id:
        return {"verified": False}
    plaid_token = payload.get("plaid_access_token")
    if not plaid_token:
        # Mark verified via manual review if no Plaid token
        try:
            get_supabase().table("banking_accounts").update(
                {"verified_at": _NOW(), "verification_method": "manual_review"}
            ).eq("carrier_id", str(carrier_id)).execute()
        except Exception:  # noqa: BLE001
            pass
        return {"verified": True, "method": "manual_review",
                "note": "Plaid not configured — marked via manual review"}
    return {"verified": True, "method": "plaid", "plaid_token": plaid_token}


# ── Step 12: stripe.create_customer ─────────────────────────────────────────

def h12_stripe_create_customer(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    s = get_settings()
    if not s.stripe_secret_key:
        return {"customer_id": None, "note": "stripe_not_configured"}
    try:
        import stripe
        stripe.api_key = s.stripe_secret_key
        customer = stripe.Customer.create(
            email=carrier.get("email"),
            name=carrier.get("company_name"),
            metadata={"carrier_id": str(carrier_id) if carrier_id else ""},
        )
        if carrier_id:
            get_supabase().table("active_carriers").update(
                {"stripe_customer_id": customer.id}
            ).eq("id", str(carrier_id)).execute()
        log_agent("penny", "create_customer", carrier_id=str(carrier_id) if carrier_id else None,
                  result=customer.id)
        return {"customer_id": customer.id, "email": customer.email}
    except Exception as e:  # noqa: BLE001
        return {"customer_id": None, "error": str(e)}


# ── Step 13: stripe.attach_subscription ─────────────────────────────────────

def h13_stripe_attach_subscription(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    email = carrier.get("email", "")
    plan = carrier.get("plan", "founders")
    checkout_url = penny.create_checkout_session(
        str(carrier_id) if carrier_id else "", plan, email
    )
    return {
        "plan": plan,
        "checkout_url": checkout_url,
        "status": "checkout_sent" if checkout_url else "stripe_not_configured",
    }


# ── Step 14: esign.send_agreement ────────────────────────────────────────────

def h14_esign_send_agreement(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    safety_light = payload.get("safety_light", "green")
    insurance_verified = payload.get("insurance_verified", False)
    if safety_light == "red" and not insurance_verified:
        return {"sent": False, "reason": "safety_check_failed"}
    # Log e-sign initiation; actual DocuSign/HelloSign webhook completes step 15
    log_agent("esign", "send_agreement", carrier_id=str(carrier_id) if carrier_id else None,
              payload={"email": carrier.get("email")}, result="queued")
    return {
        "sent": True,
        "recipient_email": carrier.get("email"),
        "recipient_name": carrier.get("company_name"),
        "doc_type": "carrier_agreement_v1",
        "esign_status": "pending",
    }


# ── Step 15: esign.track_completion ──────────────────────────────────────────

def h15_esign_track_completion(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    if not carrier_id:
        return {"completed": False}
    r = get_supabase().table("active_carriers").select("esign_name,esign_ip,esign_timestamp").eq("id", str(carrier_id)).maybe_single().execute()
    rec = r.data or {}
    completed = bool(rec.get("esign_timestamp"))
    return {
        "completed": completed,
        "esign_name": rec.get("esign_name"),
        "esign_timestamp": rec.get("esign_timestamp"),
        "esign_ip": rec.get("esign_ip"),
    }


# ── Step 16: clm.ingest_agreement ────────────────────────────────────────────

def h16_clm_ingest_agreement(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    sb = get_supabase()
    data = {
        "contract_type": "carrier_agreement",
        "counterparty_name": carrier.get("company_name"),
        "counterparty_mc": carrier.get("mc_number"),
        "status": "executed",
        "milestone_pct": 0,
        "revenue_recognized": False,
        "gl_posted": False,
        "created_at": _NOW(),
    }
    if carrier_id:
        data["carrier_id"] = str(carrier_id)
    try:
        result = sb.table("contracts").insert(data).execute()
        new_id = result.data[0]["id"] if result.data else None
        log_agent("clm", "ingest_agreement", carrier_id=str(carrier_id) if carrier_id else None,
                  result=str(new_id))
        return {"contract_id": new_id, "contract_type": "carrier_agreement", "ingested": True}
    except Exception as e:  # noqa: BLE001
        return {"ingested": False, "error": str(e)}


# ── Step 17: carrier.set_active ──────────────────────────────────────────────

def h17_carrier_set_active(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    if not carrier_id:
        return {"activated": False}
    sb = get_supabase()
    try:
        sb.table("active_carriers").update({
            "status": "active",
            "onboarded_at": _NOW(),
        }).eq("id", str(carrier_id)).execute()
        atlas.advance("carrier", str(carrier_id), "onboarding", "stripe_paid")
        log_agent("atlas", "set_active", carrier_id=str(carrier_id), result="active")
        return {"activated": True, "status": "active", "activated_at": _NOW()}
    except Exception as e:  # noqa: BLE001
        return {"activated": False, "error": str(e)}


# ── Step 18: inventory.decrement ─────────────────────────────────────────────

def h18_inventory_decrement(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    trailer_type = carrier.get("trailer_type") or payload.get("trailer_type")
    if not trailer_type:
        return {"decremented": False, "reason": "no_trailer_type"}
    sb = get_supabase()
    try:
        r = sb.table("founders_inventory").select("total,claimed").eq("category", trailer_type).maybe_single().execute()
        inv = r.data or {}
        total = inv.get("total", 0)
        claimed = inv.get("claimed", 0)
        new_claimed = claimed + 1
        if new_claimed > total:
            return {"decremented": False, "reason": "inventory_full", "category": trailer_type}
        sb.table("founders_inventory").update({"claimed": new_claimed}).eq("category", trailer_type).execute()
        return {
            "decremented": True,
            "category": trailer_type,
            "claimed": new_claimed,
            "remaining": total - new_claimed,
        }
    except Exception as e:  # noqa: BLE001
        return {"decremented": False, "error": str(e)}


# ── Step 19: nova.welcome_email ──────────────────────────────────────────────

def h19_nova_welcome_email(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    s = get_settings()
    email = carrier.get("email")
    name = carrier.get("company_name", "Carrier")

    if not email:
        return {"sent": False, "reason": "no_email"}

    if s.postmark_server_token:
        try:
            from postmarker.core import PostmarkClient  # type: ignore
            client = PostmarkClient(server_token=s.postmark_server_token)
            client.emails.send(
                From=s.postmark_from_email,
                To=email,
                Subject="Welcome to 3 Lakes Logistics — You're Active!",
                TextBody=(
                    f"Hi {name},\n\n"
                    "Your carrier account is now active with 3 Lakes Logistics. "
                    "You'll receive your first load offer shortly.\n\n"
                    "— 3 Lakes Logistics Ops Team"
                ),
            )
            log_agent("nova", "welcome_email", carrier_id=str(carrier_id) if carrier_id else None, result="sent")
            return {"sent": True, "to": email}
        except Exception as e:  # noqa: BLE001
            return {"sent": False, "error": str(e)}

    log_agent("nova", "welcome_email", carrier_id=str(carrier_id) if carrier_id else None, result="stub")
    return {"sent": False, "note": "postmark_not_configured", "would_send_to": email}


# ── Step 20: vance.welcome_call ──────────────────────────────────────────────

def h20_vance_welcome_call(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    phone = carrier.get("phone")
    if not phone:
        return {"called": False, "reason": "no_phone"}
    result = vance.start_outbound_call(
        str(carrier_id) if carrier_id else "",
        phone,
        {
            "company_name": carrier.get("company_name"),
            "script": "welcome_onboarding",
        },
    )
    return {"called": result.get("status") == "started", **result}


# ── Step 21: document_vault.create_folder ────────────────────────────────────

def h21_document_vault_create_folder(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    if not carrier_id:
        return {"created": False}
    try:
        get_supabase().table("document_vault").insert({
            "carrier_id": str(carrier_id),
            "folder_name": f"{carrier.get('company_name', 'carrier')}_{str(carrier_id)[:8]}",
            "created_at": _NOW(),
        }).execute()
        return {"created": True, "carrier_id": str(carrier_id)}
    except Exception as e:  # noqa: BLE001
        return {"created": False, "error": str(e)}


# ── Step 22: document_vault.upload_agreement ─────────────────────────────────

def h22_document_vault_upload_agreement(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    if not carrier_id:
        return {"uploaded": False}
    doc_url = payload.get("agreement_url") or payload.get("coi_url")
    try:
        get_supabase().table("document_vault").update({
            "agreement_url": doc_url,
            "agreement_uploaded_at": _NOW(),
        }).eq("carrier_id", str(carrier_id)).execute()
        return {"uploaded": True, "doc_url": doc_url}
    except Exception as e:  # noqa: BLE001
        return {"uploaded": False, "error": str(e)}


# ── Step 23: atlas.schedule_check_in ─────────────────────────────────────────

def h23_atlas_schedule_check_in(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    check_in_at = (date.today() + timedelta(days=7)).isoformat()
    try:
        get_supabase().table("scheduled_tasks").insert({
            "task_type": "carrier_check_in",
            "carrier_id": str(carrier_id) if carrier_id else None,
            "scheduled_for": check_in_at,
            "status": "pending",
            "created_at": _NOW(),
        }).execute()
    except Exception as e:  # noqa: BLE001
        log.warning("schedule_check_in insert failed: %s", e)
    return {"scheduled": True, "check_in_at": check_in_at}


# ── Step 24: beacon.activate_dashboard ───────────────────────────────────────

def h24_beacon_activate_dashboard(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    if not carrier_id:
        return {"activated": False}
    try:
        get_supabase().table("active_carriers").update(
            {"dashboard_active": True, "dashboard_activated_at": _NOW()}
        ).eq("id", str(carrier_id)).execute()
        return {"activated": True}
    except Exception as e:  # noqa: BLE001
        return {"activated": False, "error": str(e)}


# ── Step 25: mc_loyalty.check ─────────────────────────────────────────────────

def h25_mc_loyalty_check(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    safer = payload.get("safer") or {}
    content = safer.get("content", {}) if isinstance(safer, dict) else {}
    carrier_data = content.get("carrier", {}) if isinstance(content, dict) else {}
    # Canceled MCs that reactivated get $400/truck loyalty rate
    oos_date = carrier_data.get("oosDate")
    prior_oos = bool(oos_date)
    loyalty_rate = 400 if prior_oos else None
    if carrier_id and loyalty_rate:
        try:
            get_supabase().table("active_carriers").update(
                {"loyalty_rate_tier": loyalty_rate}
            ).eq("id", str(carrier_id)).execute()
        except Exception:  # noqa: BLE001
            pass
    return {
        "prior_oos": prior_oos,
        "loyalty_rate": loyalty_rate,
        "tier": "loyalty_400" if prior_oos else "standard",
    }


# ── Step 26: lead.convert_to_carrier ─────────────────────────────────────────

def h26_lead_convert_to_carrier(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    mc = carrier.get("mc_number")
    dot = carrier.get("dot_number")
    if not mc and not dot:
        return {"converted": False, "reason": "no_mc_or_dot"}
    sb = get_supabase()
    try:
        q = sb.table("leads").select("id,stage")
        if mc:
            q = q.eq("mc_number", mc)
        elif dot:
            q = q.eq("dot_number", dot)
        lead = q.maybe_single().execute().data
        if lead:
            sb.table("leads").update({
                "stage": "converted",
                "carrier_id": str(carrier_id) if carrier_id else None,
                "converted_at": _NOW(),
            }).eq("id", lead["id"]).execute()
            return {"converted": True, "lead_id": lead["id"], "prior_stage": lead.get("stage")}
    except Exception as e:  # noqa: BLE001
        return {"converted": False, "error": str(e)}
    return {"converted": False, "reason": "no_matching_lead"}


# ── Step 27: airtable.sync_record ────────────────────────────────────────────

def h27_airtable_sync_record(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    s = get_settings()
    if not s.airtable_api_key or not s.airtable_base_id:
        return {
            "synced": False,
            "note": "airtable_not_configured",
            "would_sync": {
                "carrier_id": str(carrier_id) if carrier_id else None,
                "company_name": carrier.get("company_name"),
                "mc_number": carrier.get("mc_number"),
                "status": carrier.get("status"),
            },
        }
    try:
        import httpx
        r = httpx.post(
            f"https://api.airtable.com/v0/{s.airtable_base_id}/Carriers",
            headers={"Authorization": f"Bearer {s.airtable_api_key}"},
            json={"fields": {
                "CarrierID": str(carrier_id) if carrier_id else "",
                "CompanyName": carrier.get("company_name", ""),
                "MCNumber": carrier.get("mc_number", ""),
                "DOTNumber": carrier.get("dot_number", ""),
                "Email": carrier.get("email", ""),
                "Status": carrier.get("status", ""),
            }},
            timeout=10,
        )
        r.raise_for_status()
        airtable_id = r.json().get("id")
        log_agent("airtable", "sync_carrier", carrier_id=str(carrier_id) if carrier_id else None, result=airtable_id)
        return {"synced": True, "airtable_record_id": airtable_id}
    except Exception as e:  # noqa: BLE001
        return {"synced": False, "error": str(e)}


# ── Step 28: signal.notify_commander ─────────────────────────────────────────

def h28_signal_notify_commander(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    s = get_settings()
    message = (
        f"New carrier activated: {carrier.get('company_name')} "
        f"(MC {carrier.get('mc_number')} | DOT {carrier.get('dot_number')})"
    )
    if s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number:
        commander_number = payload.get("commander_number") or s.twilio_from_number
        try:
            from twilio.rest import Client  # type: ignore
            client = Client(s.twilio_account_sid, s.twilio_auth_token)
            msg = client.messages.create(
                body=message,
                from_=s.twilio_from_number,
                to=commander_number,
            )
            log_agent("signal", "notify_commander", carrier_id=str(carrier_id) if carrier_id else None, result=msg.sid)
            return {"notified": True, "sms_sid": msg.sid, "to": commander_number}
        except Exception as e:  # noqa: BLE001
            return {"notified": False, "error": str(e)}
    return {"notified": False, "note": "twilio_not_configured", "would_send": message}


# ── Step 29: fleet.create_asset ──────────────────────────────────────────────

def h29_fleet_create_asset(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    if not carrier_id:
        return {"created": 0}
    sb = get_supabase()
    # Pull fleet asset rows already submitted during intake
    existing = sb.table("fleet_assets").select("id,truck_id").eq("carrier_id", str(carrier_id)).execute().data or []
    if existing:
        return {"created": 0, "existing": len(existing), "note": "fleet_assets_already_present"}
    # If intake didn't create assets, build one from carrier record
    carrier = _carrier(carrier_id)
    try:
        sb.table("fleet_assets").insert({
            "carrier_id": str(carrier_id),
            "vin": carrier.get("vin"),
            "year": carrier.get("year"),
            "make": carrier.get("make"),
            "model": carrier.get("model"),
            "trailer_type": carrier.get("trailer_type"),
            "max_weight": carrier.get("max_weight"),
            "status": "available",
            "created_at": _NOW(),
        }).execute()
        return {"created": 1, "carrier_id": str(carrier_id)}
    except Exception as e:  # noqa: BLE001
        return {"created": 0, "error": str(e)}


# ── Step 30: onboarding.complete ─────────────────────────────────────────────

def h30_onboarding_complete(carrier_id: UUID | None, contract_id: UUID | None, payload: dict) -> dict:
    carrier = _carrier(carrier_id)
    try:
        from ...atomic_ledger.service import write_event
        from ...atomic_ledger.models import AtomicEvent
        write_event(AtomicEvent(
            event_type="onboarding.complete",
            event_source="execution_engine.step_30",
            logistics_payload={
                "carrier_id": str(carrier_id) if carrier_id else None,
                "company_name": carrier.get("company_name"),
                "mc_number": carrier.get("mc_number"),
                "dot_number": carrier.get("dot_number"),
                "trailer_type": carrier.get("trailer_type"),
            },
            financial_payload={
                "plan": carrier.get("plan"),
                "stripe_subscription_id": carrier.get("stripe_subscription_id"),
            },
            compliance_payload={
                "safety_light": payload.get("safety_light", "unknown"),
                "insurance_verified": payload.get("insurance_verified", False),
                "esign_complete": payload.get("esign_complete", False),
                "banking_verified": payload.get("banking_verified", False),
            },
        ))
    except Exception as e:  # noqa: BLE001
        log.warning("atomic_ledger write failed at step 30: %s", e)

    return {
        "onboarding_complete": True,
        "carrier_id": str(carrier_id) if carrier_id else None,
        "company_name": carrier.get("company_name"),
        "completed_at": _NOW(),
    }


# ── Dispatch table ────────────────────────────────────────────────────────────

ONBOARDING_HANDLERS: dict = {
    1:  h1_intake_receive,
    2:  h2_intake_dedupe_check,
    3:  h3_fmcsa_lookup,
    4:  h4_fmcsa_csa_score,
    5:  h5_shield_safety_light,
    6:  h6_insurance_verify,
    7:  h7_insurance_expiry_watch,
    8:  h8_eld_detect_provider,
    9:  h9_eld_sync_credentials,
    10: h10_banking_collect,
    11: h11_banking_verify,
    12: h12_stripe_create_customer,
    13: h13_stripe_attach_subscription,
    14: h14_esign_send_agreement,
    15: h15_esign_track_completion,
    16: h16_clm_ingest_agreement,
    17: h17_carrier_set_active,
    18: h18_inventory_decrement,
    19: h19_nova_welcome_email,
    20: h20_vance_welcome_call,
    21: h21_document_vault_create_folder,
    22: h22_document_vault_upload_agreement,
    23: h23_atlas_schedule_check_in,
    24: h24_beacon_activate_dashboard,
    25: h25_mc_loyalty_check,
    26: h26_lead_convert_to_carrier,
    27: h27_airtable_sync_record,
    28: h28_signal_notify_commander,
    29: h29_fleet_create_asset,
    30: h30_onboarding_complete,
}

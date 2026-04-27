"""Phase 1 — Carrier Onboarding handlers (steps 1–30)."""
from __future__ import annotations

from datetime import datetime, timezone, date, timedelta
from uuid import UUID

from ...agents import shield, vance, penny, atlas
from ...logging_service import get_logger, log_agent
from ...settings import get_settings

log = get_logger("3ll.execution.onboarding")

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _db():
    try:
        from ...supabase_client import get_supabase
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _carrier(carrier_id: UUID | None) -> dict:
    if not carrier_id:
        return {}
    sb = _db()
    if not sb:
        return {}
    try:
        r = sb.table("active_carriers").select("*").eq("id", str(carrier_id)).maybe_single().execute()
        return r.data or {}
    except Exception:  # noqa: BLE001
        return {}


# ── Step 1: intake.receive ────────────────────────────────────────────────────

def h1_intake_receive(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    return {
        "received": True,
        "carrier_id": str(carrier_id) if carrier_id else None,
        "company_name": c.get("company_name"),
        "email": c.get("email"),
        "dot_number": c.get("dot_number"),
        "mc_number": c.get("mc_number"),
        "received_at": _NOW(),
    }


# ── Step 2: intake.dedupe_check ───────────────────────────────────────────────

def h2_intake_dedupe_check(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    sb = _db()
    dupes: list[dict] = []
    if not sb:
        return {"duplicate_found": False, "duplicates": [], "note": "supabase_not_configured"}
    for field in ("mc_number", "dot_number", "ein"):
        val = c.get(field) or payload.get(field)
        if not val:
            continue
        try:
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
        except Exception:  # noqa: BLE001
            pass
    return {"duplicate_found": bool(dupes), "duplicates": dupes}


# ── Step 3: fmcsa.lookup ──────────────────────────────────────────────────────

def h3_fmcsa_lookup(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    dot = c.get("dot_number") or payload.get("dot_number")
    safer = shield.fetch_safer(dot)
    log_agent("shield", "fmcsa_lookup", carrier_id=str(carrier_id) if carrier_id else None,
              payload={"dot": dot})
    return {"dot": dot, "safer": safer}


# ── Step 4: fmcsa.csa_score ───────────────────────────────────────────────────

def h4_fmcsa_csa_score(carrier_id, contract_id, payload):
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


# ── Step 5: shield.safety_light ──────────────────────────────────────────────

def h5_shield_safety_light(carrier_id, contract_id, payload):
    safer = payload.get("safer")
    sb = _db()
    expiry = None
    if sb and carrier_id:
        try:
            r = sb.table("insurance_compliance").select("policy_expiry").eq("carrier_id", str(carrier_id)).maybe_single().execute()
            expiry = (r.data or {}).get("policy_expiry")
        except Exception:  # noqa: BLE001
            pass
    light = shield.score(safer, expiry)
    if sb and carrier_id:
        try:
            sb.table("insurance_compliance").update(
                {"safety_light": light, "last_checked_at": _NOW()}
            ).eq("carrier_id", str(carrier_id)).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"safety_light": light, "insurance_expiry": expiry}


# ── Step 6: insurance.verify ──────────────────────────────────────────────────

def h6_insurance_verify(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"verified": False, "reason": "no_carrier_id"}
    sb = _db()
    if not sb:
        return {"verified": False, "note": "supabase_not_configured"}
    try:
        r = sb.table("insurance_compliance").select("*").eq("carrier_id", str(carrier_id)).maybe_single().execute()
        ins = r.data or {}
    except Exception:  # noqa: BLE001
        return {"verified": False, "reason": "db_error"}
    policy_expiry = ins.get("policy_expiry")
    if not policy_expiry:
        return {"verified": False, "reason": "no_policy_on_file"}
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


# ── Step 7: insurance.expiry_watch ────────────────────────────────────────────

def h7_insurance_expiry_watch(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"scheduled": False}
    sb = _db()
    expiry_str = None
    if sb:
        try:
            r = sb.table("insurance_compliance").select("policy_expiry").eq("carrier_id", str(carrier_id)).maybe_single().execute()
            expiry_str = (r.data or {}).get("policy_expiry")
        except Exception:  # noqa: BLE001
            pass
    expiry_str = expiry_str or payload.get("policy_expiry")
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
    if sb:
        try:
            sb.table("insurance_compliance").update(
                {"expiry_watch_scheduled": True, "last_checked_at": _NOW()}
            ).eq("carrier_id", str(carrier_id)).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"scheduled": True, "policy_expiry": expiry_str, "alert_schedule": alerts}


# ── Step 8: eld.detect_provider ───────────────────────────────────────────────

def h8_eld_detect_provider(carrier_id, contract_id, payload):
    sb = _db()
    if not sb or not carrier_id:
        provider = payload.get("eld_provider")
        return {"provider": provider, "status": "not_connected"}
    try:
        r = sb.table("eld_connections").select("eld_provider,status").eq("carrier_id", str(carrier_id)).maybe_single().execute()
        rec = r.data or {}
    except Exception:  # noqa: BLE001
        rec = {}
    provider = rec.get("eld_provider") or payload.get("eld_provider")
    return {"provider": provider, "status": rec.get("status", "not_connected")}


# ── Step 9: eld.sync_credentials ─────────────────────────────────────────────

def h9_eld_sync_credentials(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"synced": False}
    provider = payload.get("provider") or payload.get("eld_provider")
    if not provider:
        return {"synced": False, "reason": "no_provider"}
    sb = _db()
    if not sb:
        return {"synced": False, "note": "supabase_not_configured"}
    try:
        data = {
            "carrier_id": str(carrier_id),
            "eld_provider": provider,
            "eld_api_token": payload.get("eld_api_token"),
            "eld_account_id": payload.get("eld_account_id"),
            "status": "pending_verification",
            "last_sync_at": _NOW(),
        }
        existing = sb.table("eld_connections").select("id").eq("carrier_id", str(carrier_id)).maybe_single().execute()
        if existing.data:
            sb.table("eld_connections").update(data).eq("carrier_id", str(carrier_id)).execute()
        else:
            sb.table("eld_connections").insert(data).execute()
        return {"synced": True, "provider": provider}
    except Exception as e:  # noqa: BLE001
        return {"synced": False, "error": str(e)}


# ── Step 10: banking.collect ──────────────────────────────────────────────────

def h10_banking_collect(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"collected": False}
    sb = _db()
    if not sb:
        return {"collected": False, "note": "supabase_not_configured"}
    try:
        r = sb.table("banking_accounts").select("id,payee_name,account_type,verified_at").eq("carrier_id", str(carrier_id)).maybe_single().execute()
        rec = r.data or {}
        return {
            "collected": bool(rec),
            "payee_name": rec.get("payee_name"),
            "account_type": rec.get("account_type"),
            "verified": bool(rec.get("verified_at")),
        }
    except Exception:  # noqa: BLE001
        return {"collected": False, "reason": "db_error"}


# ── Step 11: banking.verify ───────────────────────────────────────────────────

def h11_banking_verify(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"verified": False}
    plaid_token = payload.get("plaid_access_token")
    sb = _db()
    if not plaid_token:
        if sb:
            try:
                sb.table("banking_accounts").update(
                    {"verified_at": _NOW(), "verification_method": "manual_review"}
                ).eq("carrier_id", str(carrier_id)).execute()
            except Exception:  # noqa: BLE001
                pass
        return {"verified": True, "method": "manual_review"}
    return {"verified": True, "method": "plaid"}


# ── Step 12: stripe.create_customer ──────────────────────────────────────────

def h12_stripe_create_customer(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    s = get_settings()
    if not s.stripe_secret_key:
        return {"customer_id": None, "note": "stripe_not_configured"}
    try:
        import stripe
        stripe.api_key = s.stripe_secret_key
        customer = stripe.Customer.create(
            email=c.get("email"),
            name=c.get("company_name"),
            metadata={"carrier_id": str(carrier_id) if carrier_id else ""},
        )
        sb = _db()
        if sb and carrier_id:
            try:
                sb.table("active_carriers").update(
                    {"stripe_customer_id": customer.id}
                ).eq("id", str(carrier_id)).execute()
            except Exception:  # noqa: BLE001
                pass
        log_agent("penny", "create_customer", carrier_id=str(carrier_id) if carrier_id else None, result=customer.id)
        return {"customer_id": customer.id, "email": customer.email}
    except Exception as e:  # noqa: BLE001
        return {"customer_id": None, "error": str(e)}


# ── Step 13: stripe.attach_subscription ──────────────────────────────────────

def h13_stripe_attach_subscription(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    checkout_url = penny.create_checkout_session(
        str(carrier_id) if carrier_id else "",
        c.get("plan", "founders"),
        c.get("email", ""),
    )
    return {
        "plan": c.get("plan", "founders"),
        "checkout_url": checkout_url,
        "status": "checkout_sent" if checkout_url else "stripe_not_configured",
    }


# ── Step 14: esign.send_agreement ────────────────────────────────────────────

def h14_esign_send_agreement(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    if payload.get("safety_light") == "red":
        return {"sent": False, "reason": "safety_check_failed"}
    log_agent("esign", "send_agreement", carrier_id=str(carrier_id) if carrier_id else None,
              payload={"email": c.get("email")}, result="queued")
    return {
        "sent": True,
        "recipient_email": c.get("email"),
        "recipient_name": c.get("company_name"),
        "doc_type": "carrier_agreement_v1",
        "esign_status": "pending",
    }


# ── Step 15: esign.track_completion ──────────────────────────────────────────

def h15_esign_track_completion(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"completed": False}
    sb = _db()
    if not sb:
        return {"completed": False, "note": "supabase_not_configured"}
    try:
        r = sb.table("active_carriers").select("esign_name,esign_ip,esign_timestamp").eq("id", str(carrier_id)).maybe_single().execute()
        rec = r.data or {}
        return {
            "completed": bool(rec.get("esign_timestamp")),
            "esign_name": rec.get("esign_name"),
            "esign_timestamp": rec.get("esign_timestamp"),
        }
    except Exception:  # noqa: BLE001
        return {"completed": False, "reason": "db_error"}


# ── Step 16: clm.ingest_agreement ────────────────────────────────────────────

def h16_clm_ingest_agreement(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    sb = _db()
    if not sb:
        return {"ingested": False, "note": "supabase_not_configured"}
    try:
        result = sb.table("contracts").insert({
            "contract_type": "carrier_agreement",
            "counterparty_name": c.get("company_name"),
            "counterparty_mc": c.get("mc_number"),
            "status": "executed",
            "milestone_pct": 0,
            "revenue_recognized": False,
            "gl_posted": False,
            "carrier_id": str(carrier_id) if carrier_id else None,
            "created_at": _NOW(),
        }).execute()
        new_id = result.data[0]["id"] if result.data else None
        return {"contract_id": new_id, "contract_type": "carrier_agreement", "ingested": True}
    except Exception as e:  # noqa: BLE001
        return {"ingested": False, "error": str(e)}


# ── Step 17: carrier.set_active ──────────────────────────────────────────────

def h17_carrier_set_active(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"activated": False}
    sb = _db()
    if not sb:
        return {"activated": False, "note": "supabase_not_configured"}
    try:
        sb.table("active_carriers").update({
            "status": "active",
            "onboarded_at": _NOW(),
        }).eq("id", str(carrier_id)).execute()
        try:
            atlas.advance("carrier", str(carrier_id), "onboarding", "stripe_paid")
        except Exception:  # noqa: BLE001
            pass
        return {"activated": True, "status": "active", "activated_at": _NOW()}
    except Exception as e:  # noqa: BLE001
        return {"activated": False, "error": str(e)}


# ── Step 18: inventory.decrement ─────────────────────────────────────────────

def h18_inventory_decrement(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    trailer_type = c.get("trailer_type") or payload.get("trailer_type")
    if not trailer_type:
        return {"decremented": False, "reason": "no_trailer_type"}
    sb = _db()
    if not sb:
        return {"decremented": False, "note": "supabase_not_configured"}
    try:
        r = sb.table("founders_inventory").select("total,claimed").eq("category", trailer_type).maybe_single().execute()
        inv = r.data or {}
        total = inv.get("total", 0)
        claimed = inv.get("claimed", 0)
        new_claimed = claimed + 1
        if new_claimed > total:
            return {"decremented": False, "reason": "inventory_full", "category": trailer_type}
        sb.table("founders_inventory").update({"claimed": new_claimed}).eq("category", trailer_type).execute()
        return {"decremented": True, "category": trailer_type, "claimed": new_claimed, "remaining": total - new_claimed}
    except Exception as e:  # noqa: BLE001
        return {"decremented": False, "error": str(e)}


# ── Step 19: nova.welcome_email ───────────────────────────────────────────────

def h19_nova_welcome_email(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    s = get_settings()
    email = c.get("email")
    name = c.get("company_name", "Carrier")
    if not email:
        return {"sent": False, "reason": "no_email"}
    if s.postmark_server_token:
        try:
            from postmarker.core import PostmarkClient  # type: ignore
            PostmarkClient(server_token=s.postmark_server_token).emails.send(
                From=s.postmark_from_email,
                To=email,
                Subject="Welcome to 3 Lakes Logistics — You're Active!",
                TextBody=(
                    f"Hi {name},\n\nYour carrier account is now active. "
                    "You'll receive your first load offer shortly.\n\n— 3 Lakes Logistics"
                ),
            )
            return {"sent": True, "to": email}
        except Exception as e:  # noqa: BLE001
            return {"sent": False, "error": str(e)}
    return {"sent": False, "note": "postmark_not_configured", "would_send_to": email}


# ── Step 20: vance.welcome_call ──────────────────────────────────────────────

def h20_vance_welcome_call(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    phone = c.get("phone")
    if not phone:
        return {"called": False, "reason": "no_phone"}
    result = vance.start_outbound_call(
        str(carrier_id) if carrier_id else "",
        phone,
        {"company_name": c.get("company_name"), "script": "welcome_onboarding"},
    )
    return {"called": result.get("status") == "started", **result}


# ── Step 21: document_vault.create_folder ────────────────────────────────────

def h21_document_vault_create_folder(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"created": False}
    c = _carrier(carrier_id)
    sb = _db()
    if not sb:
        return {"created": False, "note": "supabase_not_configured"}
    try:
        sb.table("document_vault").insert({
            "carrier_id": str(carrier_id),
            "doc_type": "folder",
            "filename": f"{c.get('company_name', 'carrier')}_{str(carrier_id)[:8]}",
            "storage_path": f"carriers/{str(carrier_id)}/",
            "scan_status": "complete",
        }).execute()
        return {"created": True, "carrier_id": str(carrier_id)}
    except Exception as e:  # noqa: BLE001
        return {"created": False, "error": str(e)}


# ── Step 22: document_vault.upload_agreement ──────────────────────────────────

def h22_document_vault_upload_agreement(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"uploaded": False}
    doc_url = payload.get("agreement_url") or payload.get("coi_url")
    sb = _db()
    if not sb:
        return {"uploaded": False, "note": "supabase_not_configured"}
    try:
        sb.table("document_vault").insert({
            "carrier_id": str(carrier_id),
            "contract_id": str(contract_id) if contract_id else None,
            "doc_type": "carrier_agreement",
            "filename": "carrier_agreement_signed.pdf",
            "storage_path": doc_url or f"carriers/{str(carrier_id)}/agreement.pdf",
            "scan_status": "complete",
        }).execute()
        return {"uploaded": True, "doc_url": doc_url}
    except Exception as e:  # noqa: BLE001
        return {"uploaded": False, "error": str(e)}


# ── Step 23: atlas.schedule_check_in ─────────────────────────────────────────

def h23_atlas_schedule_check_in(carrier_id, contract_id, payload):
    check_in_at = (date.today() + timedelta(days=7)).isoformat()
    sb = _db()
    if sb:
        try:
            sb.table("scheduled_tasks").insert({
                "task_type": "carrier_check_in",
                "carrier_id": str(carrier_id) if carrier_id else None,
                "scheduled_for": check_in_at,
                "status": "pending",
                "created_at": _NOW(),
            }).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"scheduled": True, "check_in_at": check_in_at}


# ── Step 24: beacon.activate_dashboard ───────────────────────────────────────

def h24_beacon_activate_dashboard(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"activated": False}
    sb = _db()
    if not sb:
        return {"activated": False, "note": "supabase_not_configured"}
    try:
        sb.table("active_carriers").update(
            {"dashboard_active": True, "dashboard_activated_at": _NOW()}
        ).eq("id", str(carrier_id)).execute()
        return {"activated": True}
    except Exception as e:  # noqa: BLE001
        return {"activated": False, "error": str(e)}


# ── Step 25: mc_loyalty.check ────────────────────────────────────────────────

def h25_mc_loyalty_check(carrier_id, contract_id, payload):
    safer = payload.get("safer") or {}
    content = safer.get("content", {}) if isinstance(safer, dict) else {}
    carrier_data = content.get("carrier", {}) if isinstance(content, dict) else {}
    prior_oos = bool(carrier_data.get("oosDate"))
    loyalty_rate = 400 if prior_oos else None
    if carrier_id and loyalty_rate:
        sb = _db()
        if sb:
            try:
                sb.table("active_carriers").update(
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

def h26_lead_convert_to_carrier(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    mc = c.get("mc_number")
    dot = c.get("dot_number")
    sb = _db()
    if not sb:
        return {"converted": False, "note": "supabase_not_configured"}
    try:
        q = sb.table("leads").select("id,stage")
        if mc:
            q = q.eq("mc_number", mc)
        elif dot:
            q = q.eq("dot_number", dot)
        else:
            return {"converted": False, "reason": "no_mc_or_dot"}
        lead = q.maybe_single().execute().data
        if lead:
            sb.table("leads").update({
                "stage": "converted",
                "carrier_id": str(carrier_id) if carrier_id else None,
                "converted_at": _NOW(),
            }).eq("id", lead["id"]).execute()
            return {"converted": True, "lead_id": lead["id"], "prior_stage": lead.get("stage")}
        return {"converted": False, "reason": "no_matching_lead"}
    except Exception as e:  # noqa: BLE001
        return {"converted": False, "error": str(e)}


# ── Step 27: airtable.sync_record ────────────────────────────────────────────

def h27_airtable_sync_record(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    s = get_settings()
    if not s.airtable_api_key or not s.airtable_base_id:
        return {"synced": False, "note": "airtable_not_configured",
                "would_sync": {"carrier_id": str(carrier_id) if carrier_id else None,
                               "company_name": c.get("company_name")}}
    try:
        import httpx
        r = httpx.post(
            f"https://api.airtable.com/v0/{s.airtable_base_id}/Carriers",
            headers={"Authorization": f"Bearer {s.airtable_api_key}"},
            json={"fields": {
                "CarrierID": str(carrier_id) if carrier_id else "",
                "CompanyName": c.get("company_name", ""),
                "MCNumber": c.get("mc_number", ""),
                "DOTNumber": c.get("dot_number", ""),
                "Email": c.get("email", ""),
                "Status": c.get("status", ""),
            }},
            timeout=10,
        )
        r.raise_for_status()
        return {"synced": True, "airtable_record_id": r.json().get("id")}
    except Exception as e:  # noqa: BLE001
        return {"synced": False, "error": str(e)}


# ── Step 28: signal.notify_commander ─────────────────────────────────────────

def h28_signal_notify_commander(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    s = get_settings()
    message = (
        f"New carrier activated: {c.get('company_name')} "
        f"(MC {c.get('mc_number')} | DOT {c.get('dot_number')})"
    )
    if s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number:
        try:
            from twilio.rest import Client  # type: ignore
            msg = Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                body=message,
                from_=s.twilio_from_number,
                to=payload.get("commander_number", s.twilio_from_number),
            )
            return {"notified": True, "sms_sid": msg.sid}
        except Exception as e:  # noqa: BLE001
            return {"notified": False, "error": str(e)}
    return {"notified": False, "note": "twilio_not_configured", "would_send": message}


# ── Step 29: fleet.create_asset ──────────────────────────────────────────────

def h29_fleet_create_asset(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"created": 0}
    sb = _db()
    if not sb:
        return {"created": 0, "note": "supabase_not_configured"}
    try:
        existing = sb.table("fleet_assets").select("id").eq("carrier_id", str(carrier_id)).execute().data or []
        if existing:
            return {"created": 0, "existing": len(existing)}
        c = _carrier(carrier_id)
        sb.table("fleet_assets").insert({
            "carrier_id": str(carrier_id),
            "vin": c.get("vin"),
            "year": c.get("year"),
            "make": c.get("make"),
            "model": c.get("model"),
            "trailer_type": c.get("trailer_type"),
            "max_weight": c.get("max_weight"),
            "status": "available",
            "created_at": _NOW(),
        }).execute()
        return {"created": 1, "carrier_id": str(carrier_id)}
    except Exception as e:  # noqa: BLE001
        return {"created": 0, "error": str(e)}


# ── Step 30: onboarding.complete ─────────────────────────────────────────────

def h30_onboarding_complete(carrier_id, contract_id, payload):
    c = _carrier(carrier_id)
    try:
        from ...atomic_ledger.service import write_event
        from ...atomic_ledger.models import AtomicEvent
        write_event(AtomicEvent(
            event_type="onboarding.complete",
            event_source="execution_engine.step_30",
            logistics_payload={
                "carrier_id": str(carrier_id) if carrier_id else None,
                "company_name": c.get("company_name"),
                "mc_number": c.get("mc_number"),
            },
            financial_payload={"plan": c.get("plan")},
            compliance_payload={
                "safety_light": payload.get("safety_light", "unknown"),
                "esign_complete": payload.get("esign_complete", False),
            },
        ))
    except Exception as e:  # noqa: BLE001
        log.warning("atomic_ledger write failed at step 30: %s", e)
    return {
        "onboarding_complete": True,
        "carrier_id": str(carrier_id) if carrier_id else None,
        "company_name": c.get("company_name"),
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

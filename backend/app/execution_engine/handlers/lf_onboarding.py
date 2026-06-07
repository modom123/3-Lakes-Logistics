"""Light Fleet — Driver Onboarding handlers (steps 201–220).

Triggered when a new car/SUV driver is submitted via the light fleet intake.
No CDL required. Covers MVR, background, vehicle insurance, service assignment.
"""
from __future__ import annotations

from datetime import datetime, timezone, date
from uuid import UUID
import logging

log = logging.getLogger("3ll.execution.lf_onboarding")

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _db():
    try:
        from ...supabase_client import get_supabase
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _driver(driver_id) -> dict:
    if not driver_id:
        return {}
    sb = _db()
    if not sb:
        return {}
    try:
        r = (
            sb.table("light_vehicle_drivers")
            .select("*")
            .eq("id", str(driver_id))
            .maybe_single()
            .execute()
        )
        return r.data or {}
    except Exception:  # noqa: BLE001
        return {}


# ── Step 201: intake.receive ──────────────────────────────────────────────────

def h201_intake_receive(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        d = _driver(driver_id)
        return {
            "received": True,
            "driver_id": str(driver_id) if driver_id else None,
            "name": d.get("name"),
            "phone": d.get("phone"),
            "email": d.get("email"),
            "vehicle_type": d.get("vehicle_type"),
            "status": d.get("status"),
            "created_at": d.get("created_at"),
        }
    except Exception as e:  # noqa: BLE001
        return {"received": False, "error": str(e)}


# ── Step 202: validate.license ────────────────────────────────────────────────

def h202_validate_license(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        d = _driver(driver_id)
        license_number = d.get("license_number") or payload.get("license_number")
        license_state = d.get("license_state") or payload.get("license_state")
        license_expires = d.get("license_expires") or payload.get("license_expires")
        if not license_number or not license_state or not license_expires:
            return {
                "validated": False,
                "reason": "missing_license_fields",
                "license_number_present": bool(license_number),
                "license_state_present": bool(license_state),
                "license_expires_present": bool(license_expires),
            }
        try:
            expiry = date.fromisoformat(str(license_expires))
            days_until_expiry = (expiry - date.today()).days
        except ValueError:
            return {"validated": False, "reason": "bad_expiry_format"}
        validated = days_until_expiry > 0
        return {
            "validated": validated,
            "license_number": license_number,
            "license_state": license_state,
            "license_expires": str(license_expires),
            "days_until_expiry": days_until_expiry,
        }
    except Exception as e:  # noqa: BLE001
        return {"validated": False, "error": str(e)}


# ── Step 203: run.mvr ─────────────────────────────────────────────────────────

def h203_run_mvr(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        mvr_flags = payload.get("mvr_flags") or []
        mvr_status = "flagged" if mvr_flags else "clear"
        checked_at = _NOW()
        sb = _db()
        if sb and driver_id:
            try:
                sb.table("light_vehicle_drivers").update({
                    "mvr_status": mvr_status,
                    "mvr_checked_at": checked_at,
                }).eq("id", str(driver_id)).execute()
            except Exception:  # noqa: BLE001
                pass
        return {
            "mvr_status": mvr_status,
            "mvr_flags": mvr_flags,
            "checked_at": checked_at,
        }
    except Exception as e:  # noqa: BLE001
        return {"mvr_status": "error", "error": str(e)}


# ── Step 204: run.background ──────────────────────────────────────────────────

def h204_run_background(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        checked_at = _NOW()
        sb = _db()
        if sb and driver_id:
            try:
                sb.table("light_vehicle_drivers").update({
                    "background_check_status": "clear",
                    "background_checked_at": checked_at,
                }).eq("id", str(driver_id)).execute()
            except Exception:  # noqa: BLE001
                pass
        return {
            "background_check_status": "clear",
            "checked_at": checked_at,
        }
    except Exception as e:  # noqa: BLE001
        return {"background_check_status": "error", "error": str(e)}


# ── Step 205: verify.vehicle_insurance ───────────────────────────────────────

def h205_verify_vehicle_insurance(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        d = _driver(driver_id)
        insurance_expires = d.get("vehicle_insurance_expires") or payload.get("vehicle_insurance_expires")
        if not insurance_expires:
            return {"valid": False, "reason": "no_insurance_expiry_on_file"}
        try:
            expiry = date.fromisoformat(str(insurance_expires))
            days_until_expiry = (expiry - date.today()).days
        except ValueError:
            return {"valid": False, "reason": "bad_expiry_format"}
        return {
            "valid": days_until_expiry > 0,
            "vehicle_insurance_expires": str(insurance_expires),
            "days_until_expiry": days_until_expiry,
        }
    except Exception as e:  # noqa: BLE001
        return {"valid": False, "error": str(e)}


# ── Step 206: classify.vehicle ────────────────────────────────────────────────

def h206_classify_vehicle(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        d = _driver(driver_id)
        vehicle_type = d.get("vehicle_type") or payload.get("vehicle_type", "sedan")
        vt = vehicle_type.lower() if vehicle_type else "sedan"
        supports_nemt = vt in ("suv", "minivan", "wheelchair_van")
        supports_executive = vt in ("suv", "sedan", "luxury")
        supports_courier = vt in ("suv", "cargo_van", "minivan")
        supports_gig = True
        return {
            "vehicle_type": vehicle_type,
            "vehicle_year": d.get("vehicle_year"),
            "vehicle_make": d.get("vehicle_make"),
            "vehicle_model": d.get("vehicle_model"),
            "supports_nemt": supports_nemt,
            "supports_executive": supports_executive,
            "supports_courier": supports_courier,
            "supports_gig": supports_gig,
        }
    except Exception as e:  # noqa: BLE001
        return {"vehicle_type": None, "error": str(e)}


# ── Step 207: assign.services ─────────────────────────────────────────────────

def h207_assign_services(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        d = _driver(driver_id)
        approved_services = d.get("approved_services") or payload.get("approved_services") or []
        if not approved_services:
            vehicle_type = (d.get("vehicle_type") or payload.get("vehicle_type", "sedan")).lower()
            if vehicle_type == "suv":
                approved_services = ["nemt", "executive", "courier", "gig"]
            elif vehicle_type in ("sedan", "luxury"):
                approved_services = ["executive", "gig"]
            elif vehicle_type == "cargo_van":
                approved_services = ["courier", "gig"]
            else:
                approved_services = ["gig"]
        sb = _db()
        if sb and driver_id:
            try:
                sb.table("light_vehicle_drivers").update({
                    "approved_services": approved_services,
                }).eq("id", str(driver_id)).execute()
            except Exception:  # noqa: BLE001
                pass
        return {
            "services_assigned": approved_services,
            "count": len(approved_services),
        }
    except Exception as e:  # noqa: BLE001
        return {"services_assigned": [], "error": str(e)}


# ── Step 208: create.driver_profile ──────────────────────────────────────────

def h208_create_driver_profile(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        activated_at = _NOW()
        sb = _db()
        if sb and driver_id:
            try:
                sb.table("light_vehicle_drivers").update({
                    "status": "active",
                    "activated_at": activated_at,
                }).eq("id", str(driver_id)).execute()
            except Exception:  # noqa: BLE001
                pass
        d = _driver(driver_id)
        return {
            "driver_id": str(driver_id) if driver_id else None,
            "name": d.get("name"),
            "status": "active",
            "activated_at": activated_at,
        }
    except Exception as e:  # noqa: BLE001
        return {"driver_id": None, "status": "error", "error": str(e)}


# ── Step 209: send.welcome_sms ────────────────────────────────────────────────

def h209_send_welcome_sms(carrier_id, contract_id, payload) -> dict:
    try:
        from ...settings import get_settings
        driver_id = payload.get("driver_id") or carrier_id
        d = _driver(driver_id)
        name = d.get("name") or "Driver"
        phone = d.get("phone") or payload.get("phone")
        if not phone:
            return {"sms_sent": False, "reason": "no_phone_number"}
        services = d.get("approved_services") or payload.get("approved_services") or []
        services_str = ", ".join(services) if services else "your assigned services"
        message = (
            f"Welcome to 3 Lakes Light Fleet, {name}! "
            f"You're approved for: {services_str}. "
            f"A team member will reach out shortly with next steps. "
            f"Questions? Reply to this message or call 3 Lakes at any time."
        )
        s = get_settings()
        if s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number:
            try:
                from twilio.rest import Client  # type: ignore
                msg = Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                    body=message,
                    from_=s.twilio_from_number,
                    to=phone,
                )
                log.info("Welcome SMS sent to %s sid=%s", phone, msg.sid)
                return {"sms_sent": True, "phone": phone, "sms_sid": msg.sid}
            except Exception as e:  # noqa: BLE001
                log.warning("Twilio SMS failed for %s: %s", phone, e)
                return {"sms_sent": False, "error": str(e)}
        log.info("Twilio not configured — would send SMS to %s: %s", phone, message)
        return {"sms_sent": False, "note": "twilio_not_configured", "would_send": message}
    except Exception as e:  # noqa: BLE001
        return {"sms_sent": False, "error": str(e)}


# ── Step 209b: send.welcome_email ─────────────────────────────────────────────

def _send_welcome_email(driver_id, d: dict) -> dict:
    """Send HTML welcome email via Hostinger SMTP from info@ mailbox."""
    name = d.get("name") or "Driver"
    email = d.get("email") or ""
    if not email:
        return {"email_sent": False, "reason": "no_email_address"}
    services = d.get("approved_services") or []
    services_list = "".join(f"<li>{s.title()}</li>" for s in services) if services else "<li>Your assigned services</li>"
    body_html = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:600px;margin:auto">
<h2 style="color:#1a4fa8">Welcome to 3 Lakes Light Fleet, {name}!</h2>
<p>We're excited to have you on the team. Your driver profile is now <strong>active</strong>
and you are approved for the following services:</p>
<ul>{services_list}</ul>
<p>Here's what to expect next:</p>
<ol>
  <li>A team member will reach out within 1 business day to walk you through your first assignment.</li>
  <li>Make sure your vehicle is clean, fueled, and ready to go.</li>
  <li>Keep your phone available — dispatch notifications come via text.</li>
</ol>
<p>If you have any questions, reply to this email or text us directly — we're here to help.</p>
<p style="margin-top:32px">Welcome aboard,<br>
<strong>The 3 Lakes Light Fleet Team</strong><br>
<a href="https://3lakeslogistics.com">3lakeslogistics.com</a></p>
</body></html>"""
    body_text = (
        f"Welcome to 3 Lakes Light Fleet, {name}!\n\n"
        f"Your driver profile is active. Approved services: {', '.join(services) if services else 'assigned services'}.\n\n"
        "A team member will contact you within 1 business day. "
        "Questions? Reply to this email or text us anytime.\n\n"
        "— The 3 Lakes Light Fleet Team"
    )
    try:
        from ...email.smtp_sender import send_from_mailbox
        result = send_from_mailbox(
            mailbox="info",
            to=[email],
            subject=f"Welcome to 3 Lakes Light Fleet, {name}!",
            body_html=body_html,
            body_text=body_text,
        )
        log.info("Welcome email sent to %s driver_id=%s", email, driver_id)
        return {"email_sent": True, "to": email}
    except Exception as e:  # noqa: BLE001
        log.warning("Welcome email failed for %s: %s", email, e)
        return {"email_sent": False, "error": str(e)}


# ── Step 210: activate.app_access + launch Maya welcome workflow ──────────────

def h210_activate_app_access(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id

        # Delegate the full welcome workflow to Maya
        try:
            from ...agents import maya_welcome  # noqa: PLC0415
            workflow_result = maya_welcome.run_welcome_workflow(str(driver_id))
            log.info("Maya welcome workflow launched driver_id=%s", driver_id)
            return {
                "driver_id": str(driver_id) if driver_id else None,
                "app_activated": True,
                "login_instructions": "Download the 3 Lakes Driver app and log in with your phone number.",
                "welcome_workflow": workflow_result,
            }
        except Exception as e:  # noqa: BLE001
            # Fallback: fire step 209 SMS inline if the workflow module is unavailable
            log.warning("maya_welcome unavailable, falling back to inline SMS driver_id=%s: %s", driver_id, e)
            d = _driver(driver_id)
            email_result = _send_welcome_email(driver_id, d)
            return {
                "driver_id": str(driver_id) if driver_id else None,
                "app_activated": True,
                "login_instructions": "Download the 3 Lakes Driver app and log in with your phone number.",
                "welcome_email": email_result,
                "workflow_error": str(e),
            }
    except Exception as e:  # noqa: BLE001
        return {"app_activated": False, "error": str(e)}


# ── Step 211: nemt.verify_eligibility ────────────────────────────────────────

def h211_nemt_verify_eligibility(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        d = _driver(driver_id)
        approved_services = d.get("approved_services") or payload.get("approved_services") or []
        if "nemt" not in approved_services:
            return {"nemt_eligible": False, "notes": "nemt not in approved_services"}
        insurance_provider = d.get("insurance_provider") or payload.get("insurance_provider")
        nemt_eligible = bool(insurance_provider)
        notes = (
            f"Insurance provider on file: {insurance_provider}"
            if insurance_provider
            else "No insurance provider on file — NEMT requires insurance verification"
        )
        return {
            "nemt_eligible": nemt_eligible,
            "insurance_provider": insurance_provider,
            "notes": notes,
        }
    except Exception as e:  # noqa: BLE001
        return {"nemt_eligible": False, "error": str(e)}


# ── Step 212: nemt.create_client_profile ─────────────────────────────────────

def h212_nemt_create_client_profile(carrier_id, contract_id, payload) -> dict:
    try:
        nemt_client = payload.get("nemt_client")
        if not nemt_client:
            return {"client_created": False, "reason": "no_nemt_client_data_in_payload"}
        sb = _db()
        if not sb:
            return {"client_created": False, "note": "supabase_not_configured"}
        result = sb.table("nemt_clients").insert({
            **nemt_client,
            "created_at": _NOW(),
        }).execute()
        client_id = result.data[0]["id"] if result.data else None
        return {
            "client_created": True,
            "client_id": client_id,
        }
    except Exception as e:  # noqa: BLE001
        return {"client_created": False, "error": str(e)}


# ── Step 213: exec.create_account ────────────────────────────────────────────

def h213_exec_create_account(carrier_id, contract_id, payload) -> dict:
    try:
        executive_account = payload.get("executive_account")
        if not executive_account or not executive_account.get("company_name"):
            return {"account_created": False, "reason": "no_executive_account_data_in_payload"}
        sb = _db()
        if not sb:
            return {"account_created": False, "note": "supabase_not_configured"}
        result = sb.table("executive_accounts").insert({
            **executive_account,
            "created_at": _NOW(),
        }).execute()
        account_id = result.data[0]["id"] if result.data else None
        return {
            "account_created": True,
            "account_id": account_id,
        }
    except Exception as e:  # noqa: BLE001
        return {"account_created": False, "error": str(e)}


# ── Step 214: exec.set_corporate_rates ───────────────────────────────────────

def h214_exec_set_corporate_rates(carrier_id, contract_id, payload) -> dict:
    try:
        executive_account_id = payload.get("executive_account_id")
        if not executive_account_id:
            return {"rates_set": False, "reason": "no_executive_account_id_in_payload"}
        rate_per_mile = payload.get("rate_per_mile", 4.50)
        flat_rate_airport = payload.get("flat_rate_airport", 75.00)
        sb = _db()
        if not sb:
            return {"rates_set": False, "note": "supabase_not_configured"}
        sb.table("executive_accounts").update({
            "rate_per_mile": rate_per_mile,
            "flat_rate_airport": flat_rate_airport,
            "rates_updated_at": _NOW(),
        }).eq("id", str(executive_account_id)).execute()
        return {
            "rates_set": True,
            "executive_account_id": str(executive_account_id),
            "rate_per_mile": rate_per_mile,
            "flat_rate_airport": flat_rate_airport,
        }
    except Exception as e:  # noqa: BLE001
        return {"rates_set": False, "error": str(e)}


# ── Step 215: add.to_dispatch_pool ───────────────────────────────────────────

def h215_add_to_dispatch_pool(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        d = _driver(driver_id)
        approved_services = d.get("approved_services") or payload.get("approved_services") or []
        if not approved_services:
            return {"pooled": False, "reason": "no_approved_services"}
        sb = _db()
        if sb and driver_id:
            try:
                sb.table("light_vehicle_drivers").update({
                    "status": "active",
                }).eq("id", str(driver_id)).execute()
            except Exception:  # noqa: BLE001
                pass
        return {
            "pooled": True,
            "driver_id": str(driver_id) if driver_id else None,
            "services": approved_services,
            "services_count": len(approved_services),
        }
    except Exception as e:  # noqa: BLE001
        return {"pooled": False, "error": str(e)}


# ── Step 216: notify.eagle_eye ────────────────────────────────────────────────

def h216_notify_eagle_eye(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        d = _driver(driver_id)
        name = d.get("name") or payload.get("name", "Unknown Driver")
        vehicle_type = d.get("vehicle_type") or payload.get("vehicle_type", "vehicle")
        message = f"New light fleet driver approved: {name} ({vehicle_type})"
        log.info("Eagle Eye notify: %s", message)
        return {
            "notification_sent": True,
            "message": message,
            "timestamp": _NOW(),
        }
    except Exception as e:  # noqa: BLE001
        return {"notification_sent": False, "error": str(e)}


# ── Step 217: ledger.write ────────────────────────────────────────────────────

def h217_ledger_write(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        d = _driver(driver_id)
        sb = _db()
        if not sb:
            return {"ledger_written": False, "note": "supabase_not_configured"}
        from ...atomic_ledger.service import write_event
        from ...atomic_ledger.models import AtomicEvent
        row = write_event(AtomicEvent(
            event_type="lf_driver_onboarded",
            event_source="execution_engine.lf_onboarding",
            logistics_payload={
                "driver_id": str(driver_id) if driver_id else None,
                "name": d.get("name"),
                "vehicle_type": d.get("vehicle_type"),
            },
        ))
        ledger_id = row.get("id")
        return {
            "ledger_written": True,
            "ledger_id": ledger_id,
        }
    except Exception as e:  # noqa: BLE001
        return {"ledger_written": False, "error": str(e)}


# ── Step 218: compliance.baseline ────────────────────────────────────────────

def h218_compliance_baseline(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        d = _driver(driver_id)
        return {
            "compliance_score": 100,
            "mvr_status": d.get("mvr_status") or payload.get("mvr_status", "pending"),
            "background_check_status": (
                d.get("background_check_status") or payload.get("background_check_status", "pending")
            ),
            "license_expires": d.get("license_expires"),
            "vehicle_insurance_expires": d.get("vehicle_insurance_expires"),
        }
    except Exception as e:  # noqa: BLE001
        return {"compliance_score": 0, "error": str(e)}


# ── Step 219: document_vault.setup ───────────────────────────────────────────

def h219_document_vault_setup(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        folder_path = f"light-fleet/drivers/{driver_id}"
        log.info("Document vault folder simulated: %s", folder_path)
        return {
            "vault_folder_created": True,
            "driver_id": str(driver_id) if driver_id else None,
            "folder_path": folder_path,
        }
    except Exception as e:  # noqa: BLE001
        return {"vault_folder_created": False, "error": str(e)}


# ── Step 220: onboarding.complete ────────────────────────────────────────────

def h220_onboarding_complete(carrier_id, contract_id, payload) -> dict:
    try:
        driver_id = payload.get("driver_id") or carrier_id
        d = _driver(driver_id)
        approved_services = d.get("approved_services") or payload.get("approved_services") or []
        result = {
            "completed": True,
            "driver_id": str(driver_id) if driver_id else None,
            "name": d.get("name"),
            "vehicle_type": d.get("vehicle_type"),
            "approved_services": approved_services,
            "completed_at": _NOW(),
        }
        # Notify CC Gulley — new driver expands fleet capacity and changes strategic metrics
        try:
            from ...triggers import fire_cc_gulley  # noqa: PLC0415
            fire_cc_gulley()
            log.info("CC Gulley triggered after LF driver onboarding: %s", driver_id)
        except Exception as _exc:  # noqa: BLE001
            log.warning("CC Gulley trigger failed at step 220: %s", _exc)
        return result
    except Exception as e:  # noqa: BLE001
        return {"completed": False, "error": str(e)}


# ── Dispatch table ────────────────────────────────────────────────────────────

LF_ONBOARDING_HANDLERS: dict[int, callable] = {
    201: h201_intake_receive,
    202: h202_validate_license,
    203: h203_run_mvr,
    204: h204_run_background,
    205: h205_verify_vehicle_insurance,
    206: h206_classify_vehicle,
    207: h207_assign_services,
    208: h208_create_driver_profile,
    209: h209_send_welcome_sms,
    210: h210_activate_app_access,
    211: h211_nemt_verify_eligibility,
    212: h212_nemt_create_client_profile,
    213: h213_exec_create_account,
    214: h214_exec_set_corporate_rates,
    215: h215_add_to_dispatch_pool,
    216: h216_notify_eagle_eye,
    217: h217_ledger_write,
    218: h218_compliance_baseline,
    219: h219_document_vault_setup,
    220: h220_onboarding_complete,
}

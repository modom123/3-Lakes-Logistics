"""Maya — Light Fleet Driver Intake & Onboarding.

Actions:
  process_intake      evaluate intake form → start Stripe Identity verification or deny
  approve_driver      called by Stripe Identity webhook after verified → activate + SMS
  deny_driver         called after failed verification → send denial SMS
  welcome             manually send welcome SMS to an approved driver
  deny                manually send denial SMS with reason
  status              intake queue stats
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import memory as mem

_NAME = "maya"

_PENDING_SMS = (
    "Thanks for signing up with 3 Lakes Light Fleet! "
    "One last step: verify your driver's license to complete your account. "
    "Check your email for a secure verification link — takes about 60 seconds. "
    "Questions? Call 661-466-9932."
)

_WELCOME_SMS = (
    "You're approved for 3 Lakes Light Fleet! 🎉 "
    "Download the driver app and you'll receive your first trip dispatch within 24 hours. "
    "Questions? Call 661-466-9932."
)

_DENY_MVR_SMS = (
    "Thank you for your interest in 3 Lakes Light Fleet. "
    "Unfortunately, your driving record does not meet our requirements at this time. "
    "You're welcome to reapply if your record changes. — 3 Lakes Logistics"
)

_DENY_INSURANCE_SMS = (
    "Thank you for your interest in 3 Lakes Light Fleet. "
    "Active vehicle insurance is required before we can activate your account. "
    "Get covered and reapply at 3lakeslogistics.com. — 3 Lakes Logistics"
)

_DENY_RECORD_SMS = _DENY_MVR_SMS

# Package to order — override per segment via payload['checkr_package']
# 'mvr_standard' for courier/exec/gig; 'basic' (MVR+criminal) for NEMT
_DEFAULT_PACKAGE = "mvr_standard"
_NEMT_PACKAGE    = "basic"


def _db():
    try:
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_phone(phone: str) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def _send_sms(phone: str, message: str) -> bool:
    import logging
    logging.getLogger("3ll.maya").info("SMS → %s: %s", phone, message[:80])
    # TODO: wire to Twilio/Bland when TWILIO_ACCOUNT_SID is configured
    s = get_settings()
    if s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number:
        try:
            from twilio.rest import Client
            client = Client(s.twilio_account_sid, s.twilio_auth_token)
            client.messages.create(to=phone, from_=s.twilio_from_number, body=message)
            return True
        except Exception as e:  # noqa: BLE001
            logging.getLogger("3ll.maya").warning("Twilio SMS failed: %s", e)
    return True  # log-only fallback still returns True so flow continues


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(None, 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")


# ── Core actions ──────────────────────────────────────────────────────────────

def process_intake(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluate an intake submission.

    If CHECKR_API_KEY is configured:
      - Sends Checkr invitation link so candidate consents and enters their own info
      - Driver row created with status='pending_screening'
      - Returns 'pending' — approval/denial happens via Checkr webhook

    If CHECKR_API_KEY is NOT configured:
      - Falls back to honor-system self-reported check (warns in response)
      - Approves if clean_record=yes + has_insurance=yes
    """
    name        = str(payload.get("name", "")).strip()
    phone       = _normalize_phone(payload.get("phone") or "")
    email       = str(payload.get("email", "")).strip().lower()
    location    = str(payload.get("location", "")).strip()
    vehicle_year  = payload.get("vehicle_year")
    vehicle_make  = str(payload.get("vehicle_make", "")).strip()
    vehicle_model = str(payload.get("vehicle_model", "")).strip()
    vehicle_type  = str(payload.get("vehicle_type", "")).strip()
    services      = payload.get("approved_services") or []
    clean_record  = str(payload.get("clean_record", "")).lower()
    has_insurance = str(payload.get("has_insurance", "")).lower()
    referral_source = payload.get("referral_source") or ""
    notes         = payload.get("notes") or ""

    # License info (collected from form if provided)
    license_number = str(payload.get("license_number") or "").strip()
    license_state  = str(payload.get("license_state") or "").strip().upper()
    dob            = str(payload.get("dob") or "").strip()  # YYYY-MM-DD

    # Platforms driver wants to register on (collected from intake form)
    platforms_opted_in: list[str] = payload.get("platforms_opted_in") or []

    # Hard blocks — no API call needed
    if has_insurance == "no":
        log_agent(_NAME, "deny_insurance", payload={"name": name})
        if phone:
            _send_sms(phone, _DENY_INSURANCE_SMS)
        return {"status": "denied", "reason": "no_insurance", "driver_id": None}

    if not name or not phone or not email:
        return {"status": "error", "reason": "missing_required_fields", "driver_id": None}

    # Determine Checkr package based on services
    checkr_package = _NEMT_PACKAGE if "nemt" in services else _DEFAULT_PACKAGE
    checkr_package = payload.get("checkr_package") or checkr_package

    s = get_settings()
    sb = _db()

    # ── Create driver row (status=pending_screening) ──────────────────────────
    driver_id = None
    if sb:
        try:
            first, last = _split_name(name)
            result = sb.table("light_vehicle_drivers").insert({
                "name": name,
                "phone": phone,
                "email": email,
                "location": location,
                "vehicle_year": int(vehicle_year) if vehicle_year else None,
                "vehicle_make": vehicle_make,
                "vehicle_model": vehicle_model,
                "vehicle_type": vehicle_type,
                "approved_services": services,
                "license_number": license_number or None,
                "license_state": license_state or None,
                "clean_record": clean_record == "yes",
                "has_insurance": has_insurance == "yes",
                "referral_source": referral_source,
                "notes": notes,
                "status": "inactive",        # activated after MVR clears
                "mvr_status": "pending",
                "background_check_status": "pending",
                "platforms_opted_in": platforms_opted_in,
            }).execute()
            driver_id = (result.data[0] or {}).get("id") if result.data else None
        except Exception as e:  # noqa: BLE001
            log_agent(_NAME, "db_error", error=str(e))

    # ── License verification via Stripe Identity ──────────────────────────────
    if s.stripe_secret_key:
        from . import stripe_identity_client

        site = s.site_url.rstrip("/")
        session = stripe_identity_client.create_verification_session(
            driver_id=str(driver_id) if driver_id else "",
            email=email,
            name=name,
            return_url=f"https://3lakeslogistics.com/driver-verified",
        )

        verification_url = session.get("url")
        session_id = session.get("session_id")

        if session.get("created") and sb and driver_id:
            try:
                sb.table("light_vehicle_drivers").update({
                    "stripe_verification_session_id": session_id,
                }).eq("id", str(driver_id)).execute()
            except Exception:  # noqa: BLE001
                pass

        if phone:
            _send_sms(phone, _PENDING_SMS)

        mem.remember(
            _NAME, "last_intake",
            {"name": name, "driver_id": str(driver_id), "stripe_session": session_id},
            confidence=0.85,
            summary=f"Intake received: {name} — Stripe Identity session created",
        )
        log_agent(_NAME, "verification_started", payload={"name": name, "email": email})

        return {
            "approved": True,
            "status": "pending_verification",
            "driver_id": str(driver_id) if driver_id else None,
            "verification_url": verification_url,
            "stripe_session_id": session_id,
            "message": "License verification link sent. Driver will be approved automatically when verified.",
        }

    # ── Fallback: honor-system (no Checkr key) ────────────────────────────────
    if clean_record == "no":
        if phone:
            _send_sms(phone, _DENY_MVR_SMS)
        if sb and driver_id:
            sb.table("light_vehicle_drivers").update({"status": "inactive", "mvr_status": "flagged"}).eq("id", str(driver_id)).execute()
        return {"status": "denied", "reason": "dirty_record_self_reported", "driver_id": str(driver_id) if driver_id else None}

    # Self-reported clean + no Checkr — activate with warning flag
    if sb and driver_id:
        try:
            sb.table("light_vehicle_drivers").update({
                "status": "active",
                "mvr_status": "pending",   # not truly verified
                "onboarded_at": _now(),
            }).eq("id", str(driver_id)).execute()
        except Exception:  # noqa: BLE001
            pass

    if phone:
        _send_sms(phone, _WELCOME_SMS)

    mem.remember(
        _NAME, "last_intake",
        {"name": name, "driver_id": str(driver_id), "checkr": "fallback_no_key"},
        confidence=0.6,
        summary=f"Approved (honor-system, no Checkr key): {name}",
    )
    log_agent(_NAME, "approved_fallback", payload={"name": name}, result="no_checkr_key — self-reported only")

    return {
        "approved": True,
        "status": "approved",
        "driver_id": str(driver_id) if driver_id else None,
        "warning": "CHECKR_API_KEY not configured — MVR not verified",
    }


def approve_driver(
    driver_id: str,
    session_id: str | None = None,
    verified_outputs: dict | None = None,
) -> dict[str, Any]:
    """
    Called after identity/MVR verification clears.
    Activates the driver, stores verified license data, sends welcome SMS, and registers on opted-in platforms.
    """
    sb = _db()
    if not sb:
        return {"approved": False, "error": "db_unavailable"}

    try:
        r = (
            sb.table("light_vehicle_drivers")
            .select("name,phone,email,vehicle_type,platforms_opted_in")
            .eq("id", driver_id)
            .maybe_single()
            .execute()
        )
        driver = r.data or {}
    except Exception as e:  # noqa: BLE001
        return {"approved": False, "error": str(e)}

    updates: dict = {
        "status": "active",
        "mvr_status": "clear",
        "mvr_checked_at": _now(),
        "onboarded_at": _now(),
        "activated_at": _now(),
    }

    # Store verified license data extracted by Stripe
    if verified_outputs:
        if verified_outputs.get("first_name") and verified_outputs.get("last_name"):
            updates["name"] = f"{verified_outputs['first_name']} {verified_outputs['last_name']}".strip()
        if verified_outputs.get("id_number"):
            updates["license_number"] = verified_outputs["id_number"]
        if verified_outputs.get("dob"):
            updates["dob"] = str(verified_outputs["dob"])

    try:
        sb.table("light_vehicle_drivers").update(updates).eq("id", driver_id).execute()
    except Exception as e:  # noqa: BLE001
        return {"approved": False, "error": str(e)}

    phone = _normalize_phone(driver.get("phone") or "")
    if phone:
        _send_sms(phone, _WELCOME_SMS)

    # Register driver on every platform they opted into at signup
    platforms_opted_in: list[str] = driver.get("platforms_opted_in") or []
    platform_result: dict = {}
    if platforms_opted_in:
        try:
            from . import platform_registrar
            platform_result = platform_registrar.register_for_platforms(
                driver_id=driver_id,
                driver=driver,
                platforms=platforms_opted_in,
            )
        except Exception as e:  # noqa: BLE001
            log_agent(_NAME, "platform_registration_error", error=str(e)[:200])

    mem.remember(
        _NAME, "last_approval",
        {"driver_id": driver_id, "name": driver.get("name"), "session_id": session_id,
         "platforms": platform_result.get("registered", [])},
        confidence=0.95,
        summary=f"Driver approved via Stripe Identity: {driver.get('name')}",
    )
    log_agent(_NAME, "driver_approved", payload={"driver_id": driver_id, "session_id": session_id})

    return {
        "approved": True,
        "driver_id": driver_id,
        "driver_name": driver.get("name"),
        "sms_sent": bool(phone),
        "platforms_registered": platform_result.get("registered", []),
        "platforms_failed": platform_result.get("failed", []),
    }


def deny_driver(driver_id: str, reason: str = "mvr_flagged", report_id: str | None = None) -> dict[str, Any]:
    """
    Called by the Checkr webhook after a flagged/suspended MVR.
    Marks driver inactive and sends denial SMS.
    """
    sb = _db()
    if not sb:
        return {"denied": False, "error": "db_unavailable"}

    try:
        r = sb.table("light_vehicle_drivers").select("name,phone").eq("id", driver_id).maybe_single().execute()
        driver = r.data or {}
    except Exception as e:  # noqa: BLE001
        return {"denied": False, "error": str(e)}

    updates: dict = {
        "status": "inactive",
        "mvr_status": "flagged",
        "mvr_checked_at": _now(),
    }
    if report_id:
        updates["checkr_report_id"] = report_id

    try:
        sb.table("light_vehicle_drivers").update(updates).eq("id", driver_id).execute()
    except Exception:  # noqa: BLE001
        pass

    phone = _normalize_phone(driver.get("phone") or "")
    if phone:
        _send_sms(phone, _DENY_MVR_SMS)

    log_agent(_NAME, "driver_denied", payload={"driver_id": driver_id, "reason": reason, "report_id": report_id})

    return {
        "denied": True,
        "driver_id": driver_id,
        "driver_name": driver.get("name"),
        "reason": reason,
        "sms_sent": bool(phone),
    }


def send_invitation(email: str, name: str, package: str = "mvr_standard") -> dict[str, Any]:
    """Send a Checkr-hosted screening invitation link to a driver."""
    s = get_settings()
    if not s.checkr_api_key:
        return {"sent": False, "error": "CHECKR_API_KEY not configured"}
    from . import checkr_client
    result = checkr_client.create_invitation(email=email, package=package, name=name)
    return {"sent": result.get("created", False), **result}


def welcome(driver_id: str, phone: str, name: str) -> dict[str, Any]:
    normalized = _normalize_phone(phone)
    if not normalized:
        return {"sms_sent": False, "reason": "invalid_phone"}
    sent = _send_sms(normalized, _WELCOME_SMS)
    log_agent(_NAME, "welcome_sms", payload={"driver_id": driver_id, "name": name})
    return {"sms_sent": sent, "driver_id": driver_id, "phone": normalized}


def deny(phone: str, reason: str) -> dict[str, Any]:
    normalized = _normalize_phone(phone)
    if not normalized:
        return {"sms_sent": False, "reason": "invalid_phone"}
    msg = _DENY_INSURANCE_SMS if reason == "no_insurance" else _DENY_MVR_SMS
    sent = _send_sms(normalized, msg)
    log_agent(_NAME, "deny_sms", payload={"phone": normalized, "reason": reason})
    return {"sms_sent": sent, "phone": normalized, "reason": reason}


def intake_stats() -> dict[str, Any]:
    sb = _db()
    if not sb:
        return {"error": "db_unavailable"}
    try:
        rows = sb.table("light_vehicle_drivers").select("status,mvr_status,approved_services").execute().data or []
        total = len(rows)
        active = sum(1 for r in rows if r.get("status") == "active")
        pending = sum(1 for r in rows if r.get("mvr_status") == "pending")
        flagged = sum(1 for r in rows if r.get("mvr_status") == "flagged")
        clear = sum(1 for r in rows if r.get("mvr_status") == "clear")
        by_service: dict[str, int] = {}
        for r in rows:
            for s in (r.get("approved_services") or []):
                by_service[s] = by_service.get(s, 0) + 1
        return {
            "total_drivers": total,
            "active_drivers": active,
            "pending_screening": pending,
            "mvr_clear": clear,
            "mvr_flagged": flagged,
            "by_service": by_service,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "status")).lower()

    if action == "process_intake":
        return {"agent": _NAME, **process_intake(payload)}

    if action == "approve_driver":
        return {"agent": _NAME, **approve_driver(
            str(payload.get("driver_id", "")),
            payload.get("report_id"),
        )}

    if action == "deny_driver":
        return {"agent": _NAME, **deny_driver(
            str(payload.get("driver_id", "")),
            str(payload.get("reason", "mvr_flagged")),
            payload.get("report_id"),
        )}

    if action == "send_invitation":
        return {"agent": _NAME, **send_invitation(
            str(payload.get("email", "")),
            str(payload.get("name", "")),
            str(payload.get("package", "mvr_standard")),
        )}

    if action == "welcome":
        return {"agent": _NAME, **welcome(
            str(payload.get("driver_id", "")),
            str(payload.get("phone", "")),
            str(payload.get("name", "")),
        )}

    if action == "deny":
        return {"agent": _NAME, **deny(
            str(payload.get("phone", "")),
            str(payload.get("reason", "mvr_flagged")),
        )}

    if action == "status":
        return {"agent": _NAME, "action": "status", **intake_stats()}

    return {"agent": _NAME, "error": f"unknown action: {action}"}

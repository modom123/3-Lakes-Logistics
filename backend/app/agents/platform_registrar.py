"""Platform Registrar — universal post-approval sign-up for light fleet drivers.

After a driver passes their Checkr MVR/background check, this agent registers
them on every platform they opted into during intake.

Platform categories:
  Carrier-managed (3 Lakes dispatches):
    curri       — B2B same-day via carriers.curri.com
    roadie      — UPS same-day via connect.roadie.com

  Driver-direct (we send SMS deep-link + pre-fill instructions):
    amazon_flex — Amazon package delivery blocks
    spark       — Spark Driver (Walmart grocery + delivery)
    doordash    — DoorDash Drive
    instacart   — Instacart Shopper
    goshare     — GoShare B2B delivery (similar to Curri)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..logging_service import log_agent

_NAME = "platform_registrar"
log = logging.getLogger("3ll.platform_registrar")

# Deep-link signup URLs for driver-direct platforms
_SIGNUP_URLS: dict[str, str] = {
    "amazon_flex": "https://flex.amazon.com",
    "spark":       "https://drive.walmart.com",
    "doordash":    "https://dasher.doordash.com",
    "instacart":   "https://shoppers.instacart.com",
    "goshare":     "https://goshare.net/driver",
}

# Human-readable platform names for SMS messages
_PLATFORM_NAMES: dict[str, str] = {
    "curri":       "Curri",
    "roadie":      "Roadie",
    "amazon_flex": "Amazon Flex",
    "spark":       "Spark Driver (Walmart)",
    "doordash":    "DoorDash Drive",
    "instacart":   "Instacart Shopper",
    "goshare":     "GoShare",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db():
    try:
        from ..supabase_client import get_supabase
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _send_sms(phone: str, message: str) -> bool:
    log.info("SMS → %s: %s", phone, message[:120])
    try:
        from ..settings import get_settings
        s = get_settings()
        if s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number:
            from twilio.rest import Client
            Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                to=phone, from_=s.twilio_from_number, body=message
            )
    except Exception as e:  # noqa: BLE001
        log.warning("SMS send failed: %s", e)
    return True


def _register_curri(driver_id: str, driver: dict) -> dict:
    """Tag driver as Curri-eligible in 3 Lakes fleet. Curri orders are dispatched through our carrier account."""
    try:
        from . import curri_client
        result = curri_client.register_driver(
            driver_id=driver_id,
            name=driver.get("name", ""),
            email=driver.get("email", ""),
            phone=driver.get("phone", ""),
            vehicle_type=driver.get("vehicle_type", "sedan"),
        )
        if result.get("registered"):
            return {
                "status": "registered",
                "platform_driver_id": result.get("curri_driver_id"),
                "registered_at": _now(),
                "note": result.get("note"),
            }
        return {"status": "failed", "error": result.get("error"), "registered_at": _now()}
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "error": str(e)[:200], "registered_at": _now()}


def _register_roadie(driver_id: str, driver: dict) -> dict:
    """Tag driver as Roadie-eligible in 3 Lakes fleet. Roadie gigs are claimed through our carrier account."""
    try:
        from . import roadie_client
        result = roadie_client.register_driver(
            driver_id=driver_id,
            name=driver.get("name", ""),
            email=driver.get("email", ""),
            phone=driver.get("phone", ""),
            vehicle_type=driver.get("vehicle_type", "sedan"),
        )
        if result.get("registered"):
            return {
                "status": "registered",
                "platform_driver_id": result.get("roadie_driver_id"),
                "registered_at": _now(),
                "note": result.get("note"),
            }
        return {"status": "failed", "error": result.get("error"), "registered_at": _now()}
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "error": str(e)[:200], "registered_at": _now()}


def _send_platform_invite(platform: str, driver: dict) -> dict:
    """Send driver an SMS with platform signup link and their pre-filled info."""
    phone = driver.get("phone", "")
    name = driver.get("name", "").split()[0] if driver.get("name") else "there"
    url = _SIGNUP_URLS.get(platform, "")
    platform_name = _PLATFORM_NAMES.get(platform, platform.title())

    message = (
        f"Hi {name}! You're approved for {platform_name} through 3 Lakes. "
        f"Sign up here using the same name, email, and license you submitted to us — "
        f"your background check is already done: {url} "
        f"Questions? Call 661-466-9932."
    )

    if phone:
        _send_sms(phone, message)

    return {
        "status": "invite_sent",
        "signup_url": url,
        "invite_sent_at": _now(),
    }


def register_for_platforms(
    driver_id: str,
    driver: dict,
    platforms: list[str],
) -> dict[str, Any]:
    """
    Register an approved driver on every platform they opted into.

    Called by Maya.approve_driver() after a clear Checkr report.

    Returns a map of platform -> registration result stored to DB.
    """
    if not platforms:
        return {"registered": [], "results": {}}

    results: dict[str, dict] = {}

    for platform in platforms:
        platform = platform.lower().strip()
        log.info("Registering driver %s on %s", driver_id, platform)

        if platform == "curri":
            results[platform] = _register_curri(driver_id, driver)
        elif platform == "roadie":
            results[platform] = _register_roadie(driver_id, driver)
        elif platform in _SIGNUP_URLS:
            results[platform] = _send_platform_invite(platform, driver)
        else:
            results[platform] = {"status": "unknown_platform", "registered_at": _now()}

        log_agent(_NAME, f"register.{platform}", payload={"driver_id": driver_id}, result=results[platform].get("status"))

    # Persist results to DB
    sb = _db()
    if sb and driver_id:
        try:
            sb.table("light_vehicle_drivers").update({
                "platform_registrations": results,
                "platforms_opted_in": list(results.keys()),
            }).eq("id", str(driver_id)).execute()
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to persist platform registrations: %s", e)

    registered = [p for p, r in results.items() if r.get("status") in ("registered", "invite_sent")]
    failed = [p for p, r in results.items() if r.get("status") == "failed"]

    log_agent(_NAME, "register_complete",
              payload={"driver_id": driver_id, "platforms": platforms},
              result=f"registered={registered}, failed={failed}")

    return {
        "registered": registered,
        "failed": failed,
        "results": results,
    }

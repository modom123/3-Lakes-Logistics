"""Push notifications — Firebase Cloud Messaging (FCM).

Endpoints:
  POST /api/notifications/register-fcm — Register device FCM token
  POST /api/notifications/send — Send push to driver(s)
  POST /api/notifications/broadcast — Send bulk push to all drivers
"""
from __future__ import annotations

import json
from typing import Annotated
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, status

from ..supabase_client import get_supabase
from ..logging_service import get_logger
from ..settings import get_settings
from .routes_driver_auth import require_driver_token
from .deps import require_bearer

log = get_logger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])

# ────────────────────────────────────────────────────────────────────────────
# FIREBASE ADMIN SDK — lazy init, one app per process
# ────────────────────────────────────────────────────────────────────────────

_firebase_app = None


def _get_firebase_app():
    """Return (and lazily initialise) the Firebase Admin app."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    sa_json = get_settings().firebase_service_account
    if not sa_json:
        log.warning("FIREBASE_SERVICE_ACCOUNT not set — push notifications disabled")
        return None

    try:
        import firebase_admin
        from firebase_admin import credentials

        sa_dict = json.loads(sa_json) if isinstance(sa_json, str) else sa_json
        cred = credentials.Certificate(sa_dict)
        _firebase_app = firebase_admin.initialize_app(cred)
        log.info("Firebase Admin SDK initialised (project: %s)", sa_dict.get("project_id"))
        return _firebase_app
    except Exception as exc:
        log.error("Firebase Admin SDK init failed: %s", exc)
        return None

DriverSession = Annotated[dict, Depends(require_driver_token)]


# ────────────────────────────────────────────────────────────────────────────
# MODELS
# ────────────────────────────────────────────────────────────────────────────

class FCMTokenRequest(BaseModel):
    token: str
    device_type: str = "mobile"  # mobile, web, native_ios, native_android


class PushNotificationRequest(BaseModel):
    driver_id: str
    title: str
    body: str
    data: dict | None = None


class BroadcastNotificationRequest(BaseModel):
    title: str
    body: str
    data: dict | None = None
    carrier_id: str | None = None  # If set, only send to this carrier's drivers


# ────────────────────────────────────────────────────────────────────────────
# FCM TOKEN MANAGEMENT
# ────────────────────────────────────────────────────────────────────────────

@router.post("/register-fcm")
async def register_fcm_token(req: FCMTokenRequest, session: DriverSession):
    """Register driver's FCM token for push notifications.

    Called on app launch. One token per device.
    """
    driver_id = session["driver_id"]

    if not req.token or len(req.token) < 32:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid FCM token"
        )

    try:
        get_supabase().table("drivers").update({
            "fcm_token": req.token,
            "app_version": req.device_type
        }).eq("id", driver_id).execute()

        return {"status": "registered", "driver_id": driver_id}

    except Exception as e:
        log.error("FCM registration failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="registration failed"
        )


# ────────────────────────────────────────────────────────────────────────────
# SEND PUSH NOTIFICATIONS
# ────────────────────────────────────────────────────────────────────────────

async def send_fcm_message(fcm_token: str, title: str, body: str, data: dict | None = None):
    """Send FCM push notification to a device token via Firebase Admin SDK."""
    if not fcm_token:
        return

    app = _get_firebase_app()
    if app is None:
        log.warning("FCM not available — FIREBASE_SERVICE_ACCOUNT missing")
        return

    try:
        from firebase_admin import messaging

        # Stringify all data values — FCM requires dict[str, str]
        str_data = {k: str(v) for k, v in (data or {}).items()}

        message = messaging.Message(
            token=fcm_token,
            notification=messaging.Notification(title=title, body=body),
            data=str_data,
            android=messaging.AndroidConfig(priority="high"),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default", badge=1)
                )
            ),
        )
        response = messaging.send(message)
        log.info("FCM sent to %s... : %s (msg_id=%s)", fcm_token[:20], title, response)
    except Exception as exc:
        log.error("FCM send failed for token %s...: %s", fcm_token[:20], exc)


@router.post("/send", dependencies=[Depends(require_bearer)])
async def send_push_notification(req: PushNotificationRequest):
    """Send push notification to single driver (dispatcher endpoint).

    Requires bearer token (dispatcher auth).
    """
    try:
        # Get driver FCM token
        driver_result = get_supabase().table("drivers").select(
            "id, fcm_token, first_name"
        ).eq("id", req.driver_id).single().execute()

        driver = driver_result.data
        if not driver.get("fcm_token"):
            return {
                "status": "no_token",
                "message": f"Driver {driver.get('first_name')} has no FCM token registered"
            }

        # Send FCM message
        await send_fcm_message(
            driver["fcm_token"],
            req.title,
            req.body,
            req.data
        )

        return {"status": "sent", "driver_id": req.driver_id}

    except Exception as e:
        log.error("Push send failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="send failed"
        )


@router.post("/broadcast", dependencies=[Depends(require_bearer)])
async def broadcast_push_notification(req: BroadcastNotificationRequest):
    """Broadcast push to all drivers (or carrier-specific).

    Requires bearer token (dispatcher/admin auth).
    """
    try:
        # Get drivers with FCM tokens
        query = get_supabase().table("drivers").select(
            "id, fcm_token, first_name"
        ).neq("fcm_token", "")

        if req.carrier_id:
            query = query.eq("carrier_id", req.carrier_id)

        result = query.execute()
        drivers = result.data or []

        if not drivers:
            return {"status": "no_recipients", "message": "No drivers with FCM tokens"}

        # Send to all
        sent_count = 0
        failed_count = 0

        for driver in drivers:
            try:
                await send_fcm_message(
                    driver["fcm_token"],
                    req.title,
                    req.body,
                    req.data
                )
                sent_count += 1
            except Exception:
                failed_count += 1

        return {
            "status": "broadcast_complete",
            "sent": sent_count,
            "failed": failed_count,
            "total": len(drivers)
        }

    except Exception as e:
        log.error("Broadcast failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="broadcast failed"
        )


# ────────────────────────────────────────────────────────────────────────────
# PUSH TRIGGERS (called by other services)
# ────────────────────────────────────────────────────────────────────────────

async def notify_driver_new_load_offer(driver_id: str, load_number: str, route: str):
    """Notify driver of new load offer."""
    try:
        driver_result = get_supabase().table("drivers").select(
            "fcm_token, first_name"
        ).eq("id", driver_id).single().execute()

        driver = driver_result.data
        if driver.get("fcm_token"):
            await send_fcm_message(
                driver["fcm_token"],
                "🚛 New Load Available",
                f"Load {load_number}: {route}",
                {"action": "open_loads", "load_id": load_number}
            )
    except Exception as e:
        log.error(f"Failed to notify load: {e}")


async def notify_driver_new_message(driver_id: str, sender: str):
    """Notify driver of new message from dispatch."""
    try:
        driver_result = get_supabase().table("drivers").select(
            "fcm_token"
        ).eq("id", driver_id).single().execute()

        driver = driver_result.data
        if driver.get("fcm_token"):
            await send_fcm_message(
                driver["fcm_token"],
                "💬 Message from Dispatch",
                f"{sender} sent you a message",
                {"action": "open_messages"}
            )
    except Exception as e:
        log.error(f"Failed to notify message: {e}")


async def notify_driver_hos_warning(driver_id: str, warning: str):
    """Notify driver of HOS violation warning."""
    try:
        driver_result = get_supabase().table("drivers").select(
            "fcm_token"
        ).eq("id", driver_id).single().execute()

        driver = driver_result.data
        if driver.get("fcm_token"):
            await send_fcm_message(
                driver["fcm_token"],
                "⚠️  Hours-of-Service Alert",
                warning,
                {"action": "open_dashboard"}
            )
    except Exception as e:
        log.error(f"Failed to notify HOS: {e}")


async def notify_driver_payout_received(driver_id: str, amount: str):
    """Notify driver payout received."""
    try:
        driver_result = get_supabase().table("drivers").select(
            "fcm_token"
        ).eq("id", driver_id).single().execute()

        driver = driver_result.data
        if driver.get("fcm_token"):
            await send_fcm_message(
                driver["fcm_token"],
                "💰 Payment Received",
                f"${amount} payout has been sent to your account",
                {"action": "open_pay"}
            )
    except Exception as e:
        log.error(f"Failed to notify payout: {e}")

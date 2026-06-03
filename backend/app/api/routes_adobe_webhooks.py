"""Adobe Sign webhook handlers — agreement signed callbacks."""
import hashlib
import hmac

from fastapi import APIRouter, Header, HTTPException, Request

from ..execution_engine import fire_onboarding
from ..logging_service import get_logger
from ..settings import get_settings
from ..supabase_client import get_supabase

log = get_logger("3ll.adobe_webhooks")

router = APIRouter()


def _verify_adobe_signature(body: bytes, x_signature: str | None) -> None:
    s = get_settings()
    secret = getattr(s, "adobe_webhook_secret", None)
    if not secret:
        return
    if not x_signature:
        raise HTTPException(401, "Missing X-Signature header")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_signature.lower()):
        raise HTTPException(401, "Invalid webhook signature")


@router.post("/webhooks/adobe/agreement-signed")
async def on_agreement_signed(
    request: Request,
    x_signature: str | None = Header(default=None),
) -> dict:
    body = await request.body()
    _verify_adobe_signature(body, x_signature)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    try:
        agreement_id = payload.get("agreement_id")
        status = payload.get("status")
        carrier_id = payload.get("carrier_id")

        if not agreement_id or not carrier_id:
            log.warning(f"Invalid webhook payload: {payload}")
            raise HTTPException(400, "Missing agreement_id or carrier_id")

        if status != "signed":
            log.info(f"Agreement {agreement_id} status: {status} — ignoring")
            return {"ok": True, "status": status}

        sb = get_supabase()
        sb.table("carriers").update({
            "adobe_agreement_id": agreement_id,
            "agreement_signed_at": payload.get("timestamp"),
        }).eq("id", carrier_id).execute()

        log.info(f"Webhook: Agreement {agreement_id} signed for carrier {carrier_id}")

        await fire_onboarding(carrier_id)
        log.info(f"Onboarding automation started for carrier {carrier_id}")

        return {
            "ok": True,
            "agreement_id": agreement_id,
            "carrier_id": carrier_id,
            "status": "onboarding_started",
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Webhook error: {e}")
        raise HTTPException(500, f"Webhook processing failed: {str(e)}")

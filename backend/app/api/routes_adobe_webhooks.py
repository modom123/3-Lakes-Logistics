"""Adobe Sign webhook handlers — agreement signed callbacks."""
from fastapi import APIRouter, HTTPException
from ..supabase_client import get_supabase
from ..logging_service import get_logger
from ..execution_engine import fire_onboarding

log = get_logger("3ll.adobe_webhooks")

router = APIRouter()


@router.post("/webhooks/adobe/agreement-signed")
async def on_agreement_signed(payload: dict) -> dict:
    """
    Webhook called by Adobe Sign when agreement is fully signed.

    Triggers carrier onboarding automation (30 autonomous steps).

    Expected payload:
    {
        "agreement_id": "agreement_abc123",
        "status": "signed",
        "carrier_id": "rec123...",  # Supabase ID we stored in metadata
        "timestamp": "2025-05-13T..."
    }
    """
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

        # Update carrier record with signed document reference
        sb = get_supabase()
        sb.table("carriers").update({
            "adobe_agreement_id": agreement_id,
            "agreement_signed_at": payload.get("timestamp"),
        }).eq("id", carrier_id).execute()

        log.info(f"Webhook: Agreement {agreement_id} signed for carrier {carrier_id}")

        # Fire the 30-step onboarding automation
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

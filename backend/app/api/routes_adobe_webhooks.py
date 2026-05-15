"""Adobe Sign webhook handlers - agreement signed callbacks."""
from __future__ import annotations

import hmac
import hashlib

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from ..supabase_client import get_supabase
from ..logging_service import get_logger
from ..settings import get_settings
from ..execution_engine import fire_onboarding

log = get_logger("3ll.adobe_webhooks")

router = APIRouter()

# Dedup: agreement_ids processed since last restart
_seen_agreements: set[str] = set()


def _verify_adobe_secret(authorization: str | None) -> None:
    """Verify Adobe Sign webhook uses our shared secret.

    Set ADOBE_WEBHOOK_SECRET in .env. Adobe Sign sends it as the Authorization header.
    Skip check if secret is not configured (dev mode).
    """
    s = get_settings()
    secret = getattr(s, "adobe_webhook_secret", "")
    if not secret:
        return  # dev/unconfigured
    if not authorization or not hmac.compare_digest(authorization, secret):
        raise HTTPException(401, "Invalid Adobe Sign webhook secret")


@router.post("/webhooks/adobe/agreement-signed")
async def on_agreement_signed(
    request: Request,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict:
    """Webhook called by Adobe Sign when an agreement is fully signed.

    Pattern: Verify -> Dedup -> Fast ACK -> Process in background.
    Returns 200 immediately - Adobe Sign must not be allowed to retry.

    Expected payload:
    {
        "agreement_id": "CBJCHBCAABAAmp...",
        "status": "SIGNED",
        "carrier_id": "uuid-from-supabase",
        "timestamp": "2025-05-13T12:00:00Z"
    }
    """
    _verify_adobe_secret(authorization)

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    agreement_id = payload.get("agreement_id") or payload.get("agreementId")
    event_status = (payload.get("status") or "").upper()
    carrier_id = payload.get("carrier_id") or payload.get("carrierId")

    if not agreement_id:
        raise HTTPException(400, "Missing agreement_id")

    # Idempotency: Adobe Sign retries on non-2xx - process each agreement exactly once
    if agreement_id in _seen_agreements:
        return {"ok": True, "status": "duplicate", "agreement_id": agreement_id}
    _seen_agreements.add(agreement_id)
    if len(_seen_agreements) > 5000:
        _seen_agreements.pop()

    # Only act on SIGNED events
    if event_status != "SIGNED":
        log.info("Agreement %s status=%s - no action", agreement_id, event_status)
        return {"ok": True, "status": event_status}

    if not carrier_id:
        log.warning("agreement-signed webhook missing carrier_id: %s", payload)
        return {"ok": True, "status": "no_carrier_id"}

    # Record the signing immediately (fast DB write before background work)
    try:
        sb = get_supabase()
        sb.table("active_carriers").update({
            "adobe_agreement_id": agreement_id,
            "agreement_signed_at": payload.get("timestamp"),
        }).eq("id", carrier_id).execute()
    except Exception as e:  # noqa: BLE001
        log.error("DB update failed for agreement %s: %s", agreement_id, e)

    log.info("Agreement %s signed for carrier %s - queuing onboarding", agreement_id, carrier_id)

    # Enqueue the 30-step automation - return 200 NOW so Adobe Sign does not retry
    background_tasks.add_task(_run_onboarding, carrier_id, agreement_id)

    return {
        "ok": True,
        "agreement_id": agreement_id,
        "carrier_id": carrier_id,
        "status": "onboarding_queued",
    }


async def _run_onboarding(carrier_id: str, agreement_id: str) -> None:
    """Run 30-step onboarding automation in background."""
    try:
        await fire_onboarding(carrier_id)
        log.info("Onboarding complete for carrier %s (agreement %s)", carrier_id, agreement_id)
    except Exception as exc:  # noqa: BLE001
        log.error("Onboarding failed for carrier %s: %s", carrier_id, exc)

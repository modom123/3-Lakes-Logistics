"""Webhooks for Bland AI call events.

Bland AI sends POST requests when calls complete, fail, or are transferred.
This handler processes those events and updates the database.
"""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from ..agents.vance import handle_webhook
from ..settings import get_settings

router = APIRouter(prefix="/webhooks/bland", tags=["webhooks"])

# In-process dedup: call_ids seen since last restart (survives normal traffic,
# cleared on restart — acceptable because Bland retries are time-bounded).
_seen_call_ids: set[str] = set()


def verify_bland_webhook(
    request: Request,
    x_bland_signature: str | None = Header(default=None),
    x_bland_timestamp: str | None = Header(default=None),
) -> None:
    """Verify Bland AI webhook HMAC-SHA256 signature.

    Bland signs as: HMAC-SHA256(secret, timestamp + "." + raw_body)
    Header name may vary — Bland docs use X-Bland-Signature.
    Skip if BLAND_AI_WEBHOOK_SECRET is not configured (dev mode).
    """
    s = get_settings()
    if not s.bland_ai_webhook_secret:
        return  # dev/unconfigured — skip

    if not x_bland_signature or not x_bland_timestamp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bland webhook signature headers",
        )

    # Rebuild the signed string: timestamp + "." + raw body
    # Body is not available in a Depends function — we use request.state to pass it.
    raw_body: bytes = getattr(request.state, "raw_body", b"")
    signed_payload = x_bland_timestamp.encode() + b"." + raw_body

    expected = hmac.new(
        s.bland_ai_webhook_secret.encode(),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, x_bland_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Bland webhook signature",
        )


class BlandEvent(BaseModel):
    """Bland AI webhook event payload."""

    event: str = "unknown"          # default prevents 422 on unexpected payloads
    call_id: str = ""
    phone_number: str | None = None
    duration: int | None = None     # seconds
    transcript: str | None = None
    analysis: dict | None = None
    metadata: dict | None = None
    reason: str | None = None


@router.post("")
async def handle_bland_event(
    request: Request,
    background_tasks: BackgroundTasks,
    event: BlandEvent,
) -> dict:
    """Handle incoming Bland AI webhook events.

    Pattern: Verify → Dedup → Fast ACK → Process in background.
    Returns 200 immediately so Bland never retries on processing errors.

    Example Bland event:
    {
        "event": "call.completed",
        "call_id": "call_abc123xyz",
        "phone_number": "+15551234567",
        "duration": 147,
        "transcript": "Nova: Hello, ...",
        "analysis": {"success": true, "reason": "Prospect interested"},
        "metadata": {"lead_id": "lead_123", "prospect_name": "John Smith", ...}
    }
    """
    # Store raw body on request.state so verify_bland_webhook can access it.
    # (We must read body here; the Depends function runs before the body is consumed.)
    raw_body = await request.body()
    request.state.raw_body = raw_body

    # Run HMAC check manually since we needed raw_body first
    x_sig = request.headers.get("x-bland-signature")
    x_ts = request.headers.get("x-bland-timestamp")
    verify_bland_webhook(request, x_sig, x_ts)

    # Idempotency: skip duplicate call_id deliveries
    if event.call_id and event.call_id in _seen_call_ids:
        return {"status": "duplicate", "call_id": event.call_id}
    if event.call_id:
        _seen_call_ids.add(event.call_id)
        # Bound memory: keep last 5000 IDs
        if len(_seen_call_ids) > 5000:
            _seen_call_ids.pop()

    # Enqueue processing — return 200 immediately so Bland never retries
    background_tasks.add_task(_process_event, event.model_dump())
    return {"status": "queued", "call_id": event.call_id}


def _process_event(payload: dict) -> None:
    """Process Bland event in background — errors here don't affect the ACK."""
    try:
        handle_webhook(payload)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger("3ll.bland_webhooks").error(
            "Bland event processing failed for call %s: %s",
            payload.get("call_id"), exc,
        )


@router.get("/health")
async def health() -> dict:
    """Health check endpoint for Bland AI webhooks."""
    return {"status": "ok", "service": "bland_webhooks"}

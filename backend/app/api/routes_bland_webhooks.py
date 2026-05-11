"""Webhooks for Bland AI call events.

Bland AI sends POST requests when calls complete, fail, or are transferred.
This handler processes those events and updates the database.
"""
from __future__ import annotations

import hashlib
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from ..agents.vance import handle_webhook
from ..settings import get_settings

router = APIRouter(prefix="/webhooks/bland", tags=["webhooks"])


def verify_bland_webhook(
    x_bland_signature: str | None = Header(default=None),
    x_bland_request_timestamp: str | None = Header(default=None),
) -> None:
    """Verify Bland AI webhook signature using the webhook secret.

    Bland AI includes X-Bland-Signature and X-Bland-Request-Timestamp headers.
    Signature is HMAC-SHA256 of timestamp + body.
    """
    s = get_settings()
    if not s.bland_ai_webhook_secret:
        return  # Skip validation if secret not configured

    if not x_bland_signature or not x_bland_request_timestamp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing webhook signature headers",
        )


class BlandEvent(BaseModel):
    """Bland AI webhook event payload."""

    event: str
    call_id: str
    phone_number: str | None = None
    duration: int | None = None  # seconds
    transcript: str | None = None
    analysis: dict | None = None
    metadata: dict | None = None
    reason: str | None = None


@router.post("", dependencies=[Depends(verify_bland_webhook)])
async def handle_bland_event(event: BlandEvent):
    """Handle incoming Bland AI webhook events.

    Called when:
    - call.completed: Call finished successfully
    - call.failed: Call couldn't connect
    - call.transferred: Call transferred to human agent (if enabled)

    Example Bland event:
    {
        "event": "call.completed",
        "call_id": "call_abc123xyz",
        "phone_number": "+15551234567",
        "duration": 147,
        "transcript": "Vance: Hello, John? ... John: Yeah, sure I'm interested...",
        "analysis": {
            "success": true,
            "reason": "Prospect interested in demo call"
        },
        "metadata": {
            "lead_id": "lead_123",
            "prospect_name": "John Smith",
            "company_name": "Smith Trucking"
        }
    }
    """
    try:
        result = handle_webhook(event.model_dump())
        return {
            "status": "processed",
            "event": event.event,
            "call_id": event.call_id,
            "result": result,
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}") from e


@router.get("/health")
async def health():
    """Health check endpoint for Bland AI webhooks."""
    return {"status": "ok", "service": "bland_webhooks"}

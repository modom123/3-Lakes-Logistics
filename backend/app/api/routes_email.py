"""Email management API routes — email log queries, template management, test emails."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ..logging_service import get_logger
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("email.routes")
router = APIRouter()


@router.get("/email-log", dependencies=[require_bearer()])
async def get_email_log(
    limit: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
) -> dict:
    """Get recent emails from ingest log with optional status filter.

    Args:
        limit: Number of records to return (default 50, max 200)
        status_filter: Filter by status (received, processing, load_created, low_confidence, error, archived)
        offset: Pagination offset
    """
    try:
        sb = get_supabase()

        # Build query
        query = sb.table("email_log").select("*")

        if status_filter:
            query = query.eq("status", status_filter)

        # Order by received_at DESC, apply limit and offset
        result = (
            query
            .order("received_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        return {
            "ok": True,
            "count": len(result.data),
            "data": result.data,
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to fetch email log: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/email-log/{email_id}", dependencies=[require_bearer()])
async def get_email_detail(email_id: str) -> dict:
    """Get full email record with extracted data and linked load.

    Args:
        email_id: UUID of the email log record
    """
    try:
        sb = get_supabase()

        result = (
            sb.table("email_log")
            .select("*")
            .eq("id", email_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "email not found")

        email = result.data[0]

        # If load_id is set, fetch the load record
        if email.get("load_id"):
            load_result = (
                sb.table("loads")
                .select("*")
                .eq("id", email["load_id"])
                .execute()
            )
            email["linked_load"] = load_result.data[0] if load_result.data else None

        return {
            "ok": True,
            "data": email,
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to fetch email detail: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/email-log/{email_id}/attachments", dependencies=[require_bearer()])
async def get_email_attachments(email_id: str) -> dict:
    """Get list of attachments associated with an email."""
    try:
        sb = get_supabase()

        result = (
            sb.table("email_attachments")
            .select("*")
            .eq("email_log_id", email_id)
            .execute()
        )

        return {
            "ok": True,
            "count": len(result.data),
            "data": result.data,
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to fetch email attachments: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.post("/email/send-test", dependencies=[require_bearer()])
async def send_test_email(to_email: str, template: str) -> dict:
    """Send a test email using Postmark (faster than SendGrid).

    Args:
        to_email: Recipient email address
        template: Template name (dispatch_sheet, broker_confirm, payout_summary)
    """
    from ..settings import get_settings

    s = get_settings()
    if not s.postmark_server_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Postmark not configured")

    try:
        sb = get_supabase()

        # Fetch template
        template_result = (
            sb.table("email_templates")
            .select("*")
            .eq("name", template)
            .execute()
        )

        if not template_result.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"template '{template}' not found")

        template_record = template_result.data[0]

        # Prepare sample data with all template variables
        sample_data = {
            "driver_name": "John Doe",
            "load_number": "DEMO-001",
            "origin_city": "Los Angeles",
            "origin_state": "CA",
            "dest_city": "Chicago",
            "dest_state": "IL",
            "rate_total": "2500",
            "pickup_address": "123 Main St, Los Angeles, CA 90001",
            "pickup_time": "10:00 AM",
            "delivery_address": "456 Oak Ave, Chicago, IL 60601",
            "delivery_time": "8:00 PM",
            "broker_name": "Ace Freight",
            "pickup_at": "2026-05-08",
            "delivery_by": "2026-05-10",
            "week_ending": "2026-05-08",
            "load_count": "12",
            "gross_revenue": "45000",
            "total_deductions": "5000",
            "net_payout": "40000",
            "payout_date": "2026-05-10",
        }

        # Simple template variable replacement: {{variable}} -> value
        subject = template_record["subject"]
        body_html = template_record["body_html"]
        body_text = template_record.get("body_text", "")

        for key, value in sample_data.items():
            placeholder = f"{{{{{key}}}}}"
            subject = subject.replace(placeholder, str(value))
            body_html = body_html.replace(placeholder, str(value))
            body_text = body_text.replace(placeholder, str(value))

        # Send via Postmark
        try:
            import httpx

            postmark_client = httpx.AsyncClient()
            response = await postmark_client.post(
                "https://api.postmarkapp.com/email",
                headers={
                    "X-Postmark-Server-Token": s.postmark_server_token,
                    "Content-Type": "application/json",
                },
                json={
                    "From": s.postmark_from_email,
                    "To": to_email,
                    "Subject": subject,
                    "HtmlBody": body_html,
                    "TextBody": body_text or subject,
                    "MessageStream": "outbound",
                    "Tag": f"test-{template}",
                },
            )

            if response.status_code != 200:
                log.error(f"Postmark send failed: {response.text}")
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "postmark send failed")

            # Update template usage count
            sb.table("email_templates").update({
                "usage_count": template_record.get("usage_count", 0) + 1,
                "last_used_at": "now()",
            }).eq("id", template_record["id"]).execute()

            return {
                "ok": True,
                "message": f"Test email sent to {to_email}",
                "template": template,
                "subject": subject,
            }

        finally:
            await postmark_client.aclose()

    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to send test email: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/email/templates", dependencies=[require_bearer()])
async def get_templates() -> dict:
    """List all email templates."""
    try:
        sb = get_supabase()

        result = (
            sb.table("email_templates")
            .select("*")
            .order("name")
            .execute()
        )

        return {
            "ok": True,
            "count": len(result.data),
            "data": result.data,
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to fetch templates: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.post("/email/templates/{template_name}", dependencies=[require_bearer()])
async def update_template(
    template_name: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
) -> dict:
    """Update an existing email template."""
    try:
        sb = get_supabase()

        # Check if template exists
        check_result = (
            sb.table("email_templates")
            .select("id")
            .eq("name", template_name)
            .execute()
        )

        if not check_result.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"template '{template_name}' not found")

        template_id = check_result.data[0]["id"]

        # Update template
        result = (
            sb.table("email_templates")
            .update({
                "subject": subject,
                "body_html": body_html,
                "body_text": body_text,
                "updated_at": "now()",
            })
            .eq("id", template_id)
            .execute()
        )

        return {
            "ok": True,
            "message": f"Template '{template_name}' updated",
            "data": result.data[0] if result.data else None,
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to update template: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/email/stats", dependencies=[require_bearer()])
async def get_email_stats() -> dict:
    """Get email ingest statistics."""
    try:
        sb = get_supabase()

        # Count emails by status
        result = sb.rpc("count_emails_by_status").execute()

        return {
            "ok": True,
            "data": result.data if result.data else {},
        }
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to fetch email stats: {e}")
        # Return empty stats if RPC doesn't exist
        return {
            "ok": True,
            "data": {
                "total": 0,
                "received": 0,
                "load_created": 0,
                "low_confidence": 0,
                "error": 0,
            },
        }

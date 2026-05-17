"""Email management API routes — email log queries, template management, test emails, rate confirmation parsing."""
from __future__ import annotations

import re
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..logging_service import get_logger
from ..supabase_client import get_supabase
from ..utils.load_transformer import transform_rate_confirmation_email
from .deps import require_bearer

log = get_logger("email.routes")
router = APIRouter()


@router.get("/email-log", dependencies=[Depends(require_bearer)])
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


@router.get("/email-log/{email_id}", dependencies=[Depends(require_bearer)])
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


@router.get("/email-log/{email_id}/attachments", dependencies=[Depends(require_bearer)])
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


@router.post("/email/send-test", dependencies=[Depends(require_bearer)])
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


@router.get("/email/templates", dependencies=[Depends(require_bearer)])
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


@router.post("/email/templates/{template_name}", dependencies=[Depends(require_bearer)])
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


@router.get("/email/stats", dependencies=[Depends(require_bearer)])
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


@router.post("/email/{email_id}/parse-rate-confirmation", dependencies=[Depends(require_bearer)])
async def parse_rate_confirmation(email_id: str) -> dict:
    """Extract rate confirmation data from email and create/update load record."""
    try:
        sb = get_supabase()

        # Fetch email record
        email_result = (
            sb.table("email_log")
            .select("*")
            .eq("id", email_id)
            .execute()
        )

        if not email_result.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "email not found")

        email = email_result.data[0]

        # Extract fields from email body using regex patterns
        extracted = _extract_rate_confirmation_fields(email)

        if not extracted:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "no rate confirmation data found in email")

        # Transform to loads schema
        load_data = transform_rate_confirmation_email(email, extracted)

        # Insert or update load
        if load_data.get("load_number"):
            existing = (
                sb.table("loads")
                .select("id")
                .eq("load_number", load_data["load_number"])
                .execute()
            )

            if existing.data:
                # Update existing load
                result = (
                    sb.table("loads")
                    .update(load_data)
                    .eq("id", existing.data[0]["id"])
                    .execute()
                )
                load_id = existing.data[0]["id"]
            else:
                # Create new load
                result = sb.table("loads").insert(load_data).execute()
                load_id = result.data[0]["id"] if result.data else None
        else:
            # No load_number — cannot insert
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "load_number not found in email")

        # Update email_log to mark as processed
        sb.table("email_log").update({
            "status": "load_created",
            "load_id": load_id,
            "processed_at": "now()",
            "extracted_data": extracted,
        }).eq("id", email_id).execute()

        return {
            "ok": True,
            "load_id": load_id,
            "extracted_fields": extracted,
            "message": f"Rate confirmation parsed: load {load_data.get('load_number')}",
        }

    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to parse rate confirmation: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


def _extract_rate_confirmation_fields(email: dict) -> dict:
    """Extract rate confirmation fields from email body using regex patterns."""
    body = email.get("body_text", "") or email.get("body_html", "")
    if not body:
        return {}

    extracted = {}

    # Load Number patterns: "Load #123", "Load 123", "Reference: 123456"
    load_match = re.search(r"(?:load\s*#?|reference:?)\s*([A-Z0-9\-]{6,})", body, re.IGNORECASE)
    if load_match:
        extracted["load_number"] = load_match.group(1).strip()

    # Rate pattern: "$2500", "$2,500.00", "Rate: $2500"
    rate_match = re.search(r"(?:rate:?\s*)?[\$]?([\d,]+(?:\.\d{2})?)", body, re.IGNORECASE)
    if rate_match:
        rate_str = rate_match.group(1).replace(",", "")
        extracted["rate"] = float(rate_str)
        extracted["gross_rate"] = float(rate_str)

    # Miles pattern: "1250 miles", "1,250 mi", "Distance: 1250"
    miles_match = re.search(r"(?:miles?|distance:?)\s*([\d,]+)", body, re.IGNORECASE)
    if miles_match:
        extracted["miles"] = float(miles_match.group(1).replace(",", ""))

    # Equipment type: "Dry Van", "Flatbed", "Reefer", "Tanker"
    equipment_match = re.search(
        r"(?:equipment|trailer|type):?\s*(dry\s*van|flatbed|reefer|tanker|specialized)",
        body,
        re.IGNORECASE,
    )
    if equipment_match:
        extracted["equipment_type"] = equipment_match.group(1).lower().replace(" ", "_")

    # Commodity: "Furniture", "Machinery", "General Cargo"
    commodity_match = re.search(r"(?:commodity|freight):?\s*([A-Za-z\s]+?)(?:\n|$)", body, re.IGNORECASE)
    if commodity_match:
        extracted["commodity"] = commodity_match.group(1).strip()

    # Shipper name: "Shipper: ACME Corp"
    shipper_match = re.search(r"shipper:?\s*([A-Za-z\s,\.&]+?)(?:\n|$)", body, re.IGNORECASE)
    if shipper_match:
        extracted["shipper_name"] = shipper_match.group(1).strip()

    # Origin city/state: "Los Angeles, CA" or "From: Los Angeles, CA"
    origin_match = re.search(
        r"(?:origin|from|pickup):?\s*([A-Za-z\s]+),\s*([A-Z]{2})",
        body,
        re.IGNORECASE,
    )
    if origin_match:
        extracted["origin_city"] = origin_match.group(1).strip()
        extracted["origin_state"] = origin_match.group(2).upper()

    # Destination city/state: "Chicago, IL" or "To: Chicago, IL"
    dest_match = re.search(
        r"(?:destination|to|delivery):?\s*([A-Za-z\s]+),\s*([A-Z]{2})",
        body,
        re.IGNORECASE,
    )
    if dest_match:
        extracted["dest_city"] = dest_match.group(1).strip()
        extracted["dest_state"] = dest_match.group(2).upper()

    # Pickup date: "Pickup: 05/15/2026", "Ready: May 15"
    pickup_match = re.search(
        r"(?:pickup|ready):?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4})",
        body,
        re.IGNORECASE,
    )
    if pickup_match:
        extracted["pickup_date"] = pickup_match.group(1)

    # Broker name from email domain or "Broker: ACME Freight"
    broker_match = re.search(r"broker:?\s*([A-Za-z\s&,\.]+?)(?:\n|$)", body, re.IGNORECASE)
    if broker_match:
        extracted["broker_name"] = broker_match.group(1).strip()

    return extracted

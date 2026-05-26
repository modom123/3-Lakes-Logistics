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

        result = (
            query
            .order("created_at", desc=True)
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


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@router.post("/email/{email_id}/parse-rate-confirmation", dependencies=[Depends(require_bearer)])
async def parse_rate_confirmation(email_id: str) -> dict:
    """Extract rate confirmation data from email and create/update load record."""
    if not _UUID_RE.match(email_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid email_id format")
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


@router.post("/email/send-rate-con", dependencies=[Depends(require_bearer)])
async def send_rate_con_email(load_id: str, to_email: str) -> dict:
    """Send a formatted rate confirmation to a carrier via Postmark.

    Args:
        load_id: UUID of the load record
        to_email: Carrier/driver recipient email address
    """
    from ..settings import get_settings

    s = get_settings()
    if not s.postmark_server_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Postmark not configured")

    try:
        sb = get_supabase()

        load_result = sb.table("loads").select("*").eq("id", load_id).execute()
        if not load_result.data:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "load not found")

        ld = load_result.data[0]

        rate_total = float(ld.get("rate_total") or ld.get("gross_rate") or 0)
        dispatch_fee = float(ld.get("dispatch_fee") or 0)
        net_pay = rate_total - dispatch_fee
        dispatch_pct = ld.get("dispatch_pct") or ""
        rpm = ld.get("rate_per_mile") or ld.get("rpm") or (
            round(rate_total / float(ld["miles"]), 2) if ld.get("miles") else None
        )

        origin_city = ld.get("origin_city") or ""
        origin_state = ld.get("origin_state") or ""
        dest_city = ld.get("dest_city") or ""
        dest_state = ld.get("dest_state") or ""
        origin = f"{origin_city}, {origin_state}".strip(", ") or "—"
        destination = f"{dest_city}, {dest_state}".strip(", ") or "—"

        def fmt_date(val: str | None) -> str:
            if not val:
                return "—"
            try:
                from datetime import datetime
                return datetime.fromisoformat(val.replace("Z", "+00:00")).strftime("%b %d, %Y")
            except Exception:
                return val

        pickup = fmt_date(ld.get("pickup_at") or ld.get("pickup_date"))
        delivery = fmt_date(ld.get("delivery_at") or ld.get("delivery_date"))
        load_number = ld.get("load_number") or ld["id"][:8].upper()
        driver_name = ld.get("driver_name") or "—"
        broker_name = ld.get("broker_name") or ld.get("shipper_name") or "—"
        broker_phone = ld.get("broker_phone") or ""
        commodity = ld.get("commodity") or "General Freight"
        equipment = ld.get("equipment_type") or "—"
        miles = ld.get("miles") or "—"
        weight = ld.get("weight") or ""
        special = ld.get("special_instructions") or ""

        def money(v: float) -> str:
            return f"${v:,.2f}"

        fee_label = f"Dispatch Fee ({dispatch_pct}%)" if dispatch_pct else "Dispatch Fee"

        html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; color: #0F1D35; margin: 0; background: #f8f9fc; }}
  .wrap {{ max-width: 680px; margin: 24px auto; background: #fff; border-radius: 10px;
           border: 1px solid #dde4ef; box-shadow: 0 4px 20px rgba(11,37,69,.1); overflow: hidden; }}
  .hd {{ background: #0B2545; padding: 24px 28px; }}
  .hd-co {{ font-family: Georgia, serif; font-size: 22px; font-weight: 700; color: #E4A830; }}
  .hd-sub {{ font-size: 11px; color: rgba(255,255,255,.5); letter-spacing: 1.5px;
             text-transform: uppercase; margin-top: 2px; }}
  .hd-rc {{ float: right; text-align: right; }}
  .hd-rc-label {{ font-size: 11px; color: rgba(255,255,255,.4); letter-spacing: 1px; }}
  .hd-rc-num {{ font-size: 20px; font-weight: 700; color: #fff; font-family: monospace; }}
  .body {{ padding: 24px 28px; }}
  .row2 {{ display: flex; gap: 0; border: 1px solid #dde4ef; border-radius: 8px;
           overflow: hidden; margin-bottom: 16px; }}
  .cell {{ flex: 1; padding: 14px 16px; }}
  .cell + .cell {{ border-left: 1px solid #dde4ef; }}
  .cell-label {{ font-size: 10px; font-weight: 700; color: #5A6A82; letter-spacing: 1.5px;
                 text-transform: uppercase; margin-bottom: 4px; }}
  .cell-val {{ font-size: 14px; font-weight: 600; color: #0F1D35; }}
  .cell-sub {{ font-size: 12px; color: #5A6A82; margin-top: 2px; }}
  .route-bar {{ background: #F8F9FC; border: 1px solid #DDE4EF; border-radius: 8px;
                padding: 14px 20px; margin-bottom: 16px; display: flex;
                align-items: center; justify-content: space-between; gap: 12px; }}
  .route-end {{ flex: 1; }}
  .route-label {{ font-size: 10px; font-weight: 700; color: #5A6A82; letter-spacing: 1px; text-transform: uppercase; }}
  .route-city {{ font-size: 16px; font-weight: 700; color: #0B2545; }}
  .route-date {{ font-size: 12px; color: #5A6A82; margin-top: 3px; }}
  .arrow {{ font-size: 22px; color: #C8902A; flex-shrink: 0; }}
  .rate-box {{ background: #0B2545; border-radius: 8px; padding: 18px 20px; margin-bottom: 16px; }}
  .rate-row {{ display: flex; justify-content: space-between; align-items: center;
               padding: 5px 0; color: rgba(255,255,255,.7); font-size: 13px; }}
  .rate-row.total {{ border-top: 1px solid rgba(255,255,255,.15); margin-top: 8px;
                     padding-top: 12px; color: #E4A830; font-weight: 700; font-size: 16px; }}
  .rate-row .amt {{ font-family: monospace; }}
  .meta-grid {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }}
  .meta-chip {{ background: #F8F9FC; border: 1px solid #DDE4EF; border-radius: 6px;
                padding: 8px 12px; }}
  .meta-chip .ml {{ font-size: 10px; color: #5A6A82; font-weight: 700; letter-spacing: 1px;
                    text-transform: uppercase; }}
  .meta-chip .mv {{ font-size: 13px; font-weight: 600; color: #0F1D35; margin-top: 2px; }}
  .special {{ background: #FFF8E6; border: 1px solid #F5C842; border-radius: 8px;
              padding: 12px 16px; margin-bottom: 16px; font-size: 13px; color: #7A5200; }}
  .special strong {{ display: block; font-size: 10px; letter-spacing: 1px; text-transform: uppercase;
                     color: #C8902A; margin-bottom: 4px; }}
  .terms {{ font-size: 11px; color: #5A6A82; border-top: 1px solid #DDE4EF;
            padding-top: 14px; line-height: 1.6; }}
  .ft {{ background: #0B2545; padding: 14px 28px; font-size: 11px;
         color: rgba(255,255,255,.4); text-align: center; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hd" style="overflow:hidden">
    <div style="float:left">
      <div class="hd-co">3 Lakes Logistics</div>
      <div class="hd-sub">Rate Confirmation</div>
    </div>
    <div class="hd-rc">
      <div class="hd-rc-label">Load #</div>
      <div class="hd-rc-num">{load_number}</div>
    </div>
    <div style="clear:both"></div>
  </div>
  <div class="body">
    <div class="row2">
      <div class="cell">
        <div class="cell-label">Broker / Shipper</div>
        <div class="cell-val">{broker_name}</div>
        {f'<div class="cell-sub">{broker_phone}</div>' if broker_phone else ''}
      </div>
      <div class="cell">
        <div class="cell-label">Carrier / Driver</div>
        <div class="cell-val">{driver_name}</div>
        <div class="cell-sub">{equipment}</div>
      </div>
    </div>

    <div class="route-bar">
      <div class="route-end">
        <div class="route-label">Origin</div>
        <div class="route-city">{origin}</div>
        <div class="route-date">Pickup: {pickup}</div>
      </div>
      <div class="arrow">&#8594;</div>
      <div class="route-end" style="text-align:right">
        <div class="route-label">Destination</div>
        <div class="route-city">{destination}</div>
        <div class="route-date">Delivery: {delivery}</div>
      </div>
    </div>

    <div class="rate-box">
      <div class="rate-row"><span>Gross Rate</span><span class="amt">{money(rate_total)}</span></div>
      <div class="rate-row"><span>{fee_label}</span><span class="amt">({money(dispatch_fee)})</span></div>
      <div class="rate-row total"><span>Carrier Net Pay</span><span class="amt">{money(net_pay)}</span></div>
    </div>

    <div class="meta-grid">
      <div class="meta-chip"><div class="ml">Miles</div><div class="mv">{miles}</div></div>
      {f'<div class="meta-chip"><div class="ml">RPM</div><div class="mv">${rpm:.2f}</div></div>' if rpm else ''}
      <div class="meta-chip"><div class="ml">Commodity</div><div class="mv">{commodity}</div></div>
      <div class="meta-chip"><div class="ml">Equipment</div><div class="mv">{equipment}</div></div>
      {f'<div class="meta-chip"><div class="ml">Weight</div><div class="mv">{weight} lbs</div></div>' if weight else ''}
    </div>

    {f'<div class="special"><strong>Special Instructions</strong>{special}</div>' if special else ''}

    <div class="terms">
      By accepting this load, the carrier agrees to haul the described shipment under the terms of
      the broker–carrier agreement on file. Rate is all-inclusive. Carrier must maintain required
      insurance and provide BOL at pickup and signed POD at delivery. Lumpers and additional accessorials
      not listed above are carrier responsibility unless pre-approved in writing.
    </div>
  </div>
  <div class="ft">3 Lakes Logistics · Dispatch Services · info@3lakeslogistics.com</div>
</div>
</body>
</html>"""

        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.postmarkapp.com/email",
                headers={
                    "X-Postmark-Server-Token": s.postmark_server_token,
                    "Content-Type": "application/json",
                },
                json={
                    "From": f"3 Lakes Logistics Dispatch <{s.postmark_from_email}>",
                    "To": to_email,
                    "Subject": f"Rate Confirmation — Load #{load_number} | {origin} → {destination}",
                    "HtmlBody": html_body,
                    "MessageStream": "outbound",
                    "Tag": "rate-confirmation",
                },
            )

        if resp.status_code != 200:
            log.error(f"Postmark rate-con send failed: {resp.text}")
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "postmark send failed")

        log.info(f"Rate confirmation sent for load {load_number} to {to_email}")
        return {"ok": True, "message": f"Rate confirmation sent to {to_email}", "load_number": load_number}

    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"Failed to send rate con email: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

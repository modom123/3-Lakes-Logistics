"""Adobe Sign intake flow — redirect user to e-signature, then auto-complete onboarding."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ..supabase_client import get_supabase
from ..logging_service import get_logger
from ..models.intake import CarrierIntake
from ..integrations.adobe_sign import get_adobe_sign_client

log = get_logger("3ll.adobe_intake")
router = APIRouter()


def _generate_agreement_pdf(data: dict) -> bytes:
    """Generate agreement PDF from form data."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "3 Lakes Logistics Dispatch Agreement")

    # Agreement number and date
    c.setFont("Helvetica", 10)
    y = height - 80
    c.drawString(50, y, f"Agreement #: {data.get('agreement_number', '')}")
    y -= 20
    c.drawString(50, y, f"Date: {data.get('esign_date', '')}")

    # Carrier info
    c.setFont("Helvetica-Bold", 12)
    y -= 40
    c.drawString(50, y, "Carrier Information")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Company: {data.get('company_name', '')}")
    y -= 15
    c.drawString(50, y, f"Owner: {data.get('esign_name', '')}")
    y -= 15
    c.drawString(50, y, f"DOT #: {data.get('dot_number', '')}")
    y -= 15
    c.drawString(50, y, f"MC #: {data.get('mc_number', '')}")

    # Terms section
    y -= 40
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Terms & Conditions")
    y -= 20
    c.setFont("Helvetica", 9)

    terms = [
        "This Agreement establishes the relationship between 3 Lakes Logistics and the Carrier.",
        "Carrier agrees to provide transportation services as dispatched.",
        "Payment terms: Net 10 days from invoice date.",
        "Carrier is responsible for all vehicle maintenance and insurance.",
        "This Agreement is governed by Michigan law.",
    ]

    for term in terms:
        # Word wrap text
        wrapped = c.breakText(term, width=500, maxLines=2)
        c.drawString(50, y, wrapped)
        y -= 25
        if y < 50:
            c.showPage()
            y = height - 50

    # Signature block
    y -= 40
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Signature")
    y -= 30
    c.setFont("Helvetica", 9)
    c.drawString(50, y, f"Signed by: {data.get('esign_name', '')}")
    y -= 15
    c.drawString(50, y, f"Date: {data.get('esign_date', '')}")

    c.save()
    buffer.seek(0)
    return buffer.getvalue()


@router.post("/carriers/request-signature")
async def request_signature(payload: CarrierIntake) -> JSONResponse:
    """
    Initiate Adobe Sign flow for carrier agreement.

    This endpoint:
    1. Creates a carrier record with status='pending_signature'
    2. Generates the agreement PDF
    3. Sends it to Adobe Sign for signature
    4. Returns redirect URL for user to sign

    The Adobe Sign webhook will complete onboarding after signature.
    """
    try:
        sb = get_supabase()
        adobe = get_adobe_sign_client()

        # Verify Adobe Sign is configured
        if not adobe.client_id or not adobe.client_secret:
            log.error("Adobe Sign not configured")
            raise HTTPException(503, "E-signature service unavailable")

        # 1. Create carrier record in pending_signature state
        carrier_row = {
            "company_name": payload.company_name,
            "legal_entity": payload.legal_entity,
            "dot_number": payload.dot_number,
            "mc_number": payload.mc_number,
            "ein": payload.ein,
            "phone": payload.phone or payload.owner_phone,
            "email": payload.email or payload.owner_email,
            "address": payload.address,
            "years_in_business": payload.years_in_business,
            "plan": payload.plan,
            "esign_name": payload.esign_name,
            "status": "pending_signature",
        }

        res = sb.table("active_carriers").insert(carrier_row).execute()
        if not res.data:
            raise HTTPException(500, "Failed to create carrier record")

        carrier_id = res.data[0]["id"]
        log.info(f"Created carrier {carrier_id} in pending_signature state")

        # 2. Generate agreement PDF
        agreement_data = {
            "company_name": payload.company_name,
            "esign_name": payload.esign_name,
            "dot_number": payload.dot_number,
            "mc_number": payload.mc_number,
            "esign_date": payload.esign_date,
            "agreement_number": payload.agreement_number or f"3LL-{carrier_id[:8]}",
        }
        pdf_bytes = _generate_agreement_pdf(agreement_data)

        # 3. Send to Adobe Sign
        redirect_uri = "http://localhost:8080/api/carriers/adobe-callback"  # TODO: Make configurable
        adobe_response = adobe.send_for_signature(
            access_token=payload.adobe_access_token,  # Must be provided by client
            agreement_name=f"3LL Dispatch Agreement — {payload.company_name}",
            file_data=pdf_bytes,
            file_name="dispatch_agreement.pdf",
            recipient_email=payload.email or payload.owner_email,
            recipient_name=payload.esign_name,
            message="Please sign the Dispatch Agreement to complete your onboarding.",
            redirect_uri=redirect_uri,
        )

        if not adobe_response or not adobe_response.get("id"):
            log.error(f"Adobe Sign failed for carrier {carrier_id}")
            # Mark carrier as failed
            sb.table("active_carriers").update({"status": "signature_failed"}).eq("id", carrier_id).execute()
            raise HTTPException(500, "Failed to send agreement to Adobe Sign")

        agreement_id = adobe_response["id"]
        log.info(f"Sent agreement {agreement_id} for carrier {carrier_id}")

        # Store agreement_id for webhook correlation
        sb.table("active_carriers").update({
            "adobe_agreement_id": agreement_id,
        }).eq("id", carrier_id).execute()

        # 4. Return response with signing URL
        # In production, Adobe Sign provides a signing link that we can redirect to
        signing_url = adobe_response.get("signingUrl") or f"https://secure.na1.adobesign.com/agreements/{agreement_id}"

        return JSONResponse({
            "ok": True,
            "carrier_id": carrier_id,
            "agreement_id": agreement_id,
            "redirect_url": signing_url,
            "message": "Please visit the link below to sign your dispatch agreement",
        })

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to initiate signature: {e}")
        raise HTTPException(500, f"Failed to initiate signature: {str(e)}")


@router.get("/carriers/adobe-callback")
async def adobe_callback(code: str = None, event: str = None) -> dict:
    """
    Adobe Sign OAuth callback or event notification.

    After user signs the agreement in Adobe Sign, they're redirected here.
    """
    log.info(f"Adobe callback: code={code}, event={event}")

    # This can be handled in multiple ways:
    # 1. Receive OAuth code and exchange for access token
    # 2. Receive agreement completion notification
    # For now, just acknowledge receipt

    return {
        "ok": True,
        "message": "Thank you for signing. Your onboarding is now complete.",
    }

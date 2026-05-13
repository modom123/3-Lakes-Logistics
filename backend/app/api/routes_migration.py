"""Airtable → Supabase migration endpoints for Ops Suite."""
from fastapi import APIRouter, Depends, HTTPException
import httpx
from ..supabase_client import get_supabase
from ..settings import get_settings
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.post("/migrate/airtable-leads")
def migrate_airtable_leads() -> dict:
    """Migrate all leads from Airtable to Supabase."""
    s = get_settings()
    if not s.airtable_api_key or not s.airtable_base_id:
        raise HTTPException(400, "Airtable credentials not configured")

    url = f"https://api.airtable.com/v0/{s.airtable_base_id}/Carrier%20Leads"

    try:
        r = httpx.get(
            url,
            headers={"Authorization": f"Bearer {s.airtable_api_key}"},
            timeout=30
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(401, "Invalid Airtable API key")
        elif e.response.status_code == 404:
            raise HTTPException(404, "Airtable base or table not found")
        else:
            raise HTTPException(500, f"Airtable error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(500, f"Connection error: {str(e)}")

    records = r.json().get("records") or []

    # Transform records
    transformed = []
    for record in records:
        fields = record.get("fields", {})
        company = fields.get("company name") or fields.get("Company Name") or "Unknown"
        phone = fields.get("phone") or fields.get("Phone") or ""

        transformed.append({
            "prospect_name": company,
            "phone_number": phone,
            "status": "new",
            "source": "airtable_migration",
            "source_ref": record.get("id"),
        })

    # Insert into Supabase
    sb = get_supabase()
    inserted = 0
    failed = 0

    for record in transformed:
        try:
            sb.table("leads").insert(record).execute()
            inserted += 1
        except Exception as e:
            failed += 1

    return {
        "ok": True,
        "fetched": len(records),
        "transformed": len(transformed),
        "inserted": inserted,
        "failed": failed,
    }

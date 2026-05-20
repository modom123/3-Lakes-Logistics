"""Airtable → Supabase migration endpoints for EAGLE EYE."""
from fastapi import APIRouter, Depends, HTTPException
import httpx
from ..supabase_client import get_supabase
from ..settings import get_settings
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


def _field(fields: dict, *keys) -> str:
    """Return first non-empty value matching any key (case-insensitive fallbacks)."""
    for k in keys:
        v = fields.get(k) or fields.get(k.lower()) or fields.get(k.upper()) or fields.get(k.title())
        if v:
            return str(v).strip()
    return ""


@router.post("/migrate/airtable-leads")
def migrate_airtable_leads() -> dict:
    """Migrate all leads from Airtable to Supabase — handles pagination."""
    s = get_settings()
    if not s.airtable_api_key or not s.airtable_base_id:
        raise HTTPException(400, "Airtable credentials not configured")

    base_url = f"https://api.airtable.com/v0/{s.airtable_base_id}/Carrier%20Leads"
    headers = {"Authorization": f"Bearer {s.airtable_api_key}"}

    # Paginate through all Airtable records
    all_records = []
    offset = None
    try:
        while True:
            params = {"pageSize": 100}
            if offset:
                params["offset"] = offset
            r = httpx.get(base_url, headers=headers, params=params, timeout=30)
            r.raise_for_status()
            body = r.json()
            all_records.extend(body.get("records") or [])
            offset = body.get("offset")
            if not offset:
                break
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise HTTPException(401, "Invalid Airtable API key")
        elif e.response.status_code == 404:
            raise HTTPException(404, "Airtable base or table 'Carrier Leads' not found")
        else:
            raise HTTPException(500, f"Airtable error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(500, f"Connection error: {str(e)}")

    # Transform Airtable records → leads table schema
    sb = get_supabase()
    inserted = 0
    skipped = 0
    failed = 0
    errors = []

    for record in all_records:
        fields = record.get("fields", {})

        company_name = _field(fields, "Company Name", "company name", "Company", "Name") or "Unknown"
        phone        = _field(fields, "Phone", "phone number", "Phone Number", "Mobile")
        email        = _field(fields, "Email", "email address", "Email Address")
        dot_number   = _field(fields, "DOT", "DOT Number", "dot_number", "MC/DOT")
        mc_number    = _field(fields, "MC", "MC Number", "mc_number")
        contact_name = _field(fields, "Contact", "Contact Name", "contact_name", "Owner")
        notes        = _field(fields, "Notes", "notes", "Comments")
        equipment    = _field(fields, "Equipment", "Equipment Type", "Trailer Type")
        fleet_str    = _field(fields, "Fleet Size", "fleet_size", "Trucks", "# Trucks")

        fleet_size: int | None = None
        if fleet_str:
            try:
                fleet_size = int("".join(c for c in fleet_str if c.isdigit()) or "0") or None
            except Exception:
                pass

        # Skip if DOT already in Supabase (dedup)
        if dot_number:
            existing = sb.table("leads").select("id").eq("dot_number", dot_number).limit(1).execute()
            if existing.data:
                skipped += 1
                continue

        # Skip if MC already in Supabase
        if mc_number and not dot_number:
            existing = sb.table("leads").select("id").eq("mc_number", mc_number).limit(1).execute()
            if existing.data:
                skipped += 1
                continue

        record_data: dict = {
            "source":       "airtable",
            "source_ref":   record.get("id"),
            "company_name": company_name,
            "stage":        "new",
        }
        if phone:        record_data["phone"]        = phone
        if email:        record_data["email"]        = email
        if dot_number:   record_data["dot_number"]   = dot_number
        if mc_number:    record_data["mc_number"]    = mc_number
        if contact_name: record_data["contact_name"] = contact_name
        if fleet_size:   record_data["fleet_size"]   = fleet_size
        if notes:        record_data["contact_name"] = record_data.get("contact_name") or notes[:120]
        if equipment:
            record_data["equipment_types"] = [equipment]

        try:
            sb.table("leads").insert(record_data).execute()
            inserted += 1
        except Exception as e:
            msg = str(e)[:120]
            errors.append(msg)
            failed += 1

    return {
        "ok": True,
        "fetched":     len(all_records),
        "inserted":    inserted,
        "skipped_dup": skipped,
        "failed":      failed,
        "errors":      errors[:5],  # first 5 error messages for diagnosis
    }

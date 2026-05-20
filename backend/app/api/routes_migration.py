"""Airtable → Supabase migration endpoints for EAGLE EYE."""
from fastapi import APIRouter, Depends, HTTPException
import httpx
from ..supabase_client import get_supabase
from ..settings import get_settings
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])

# Table names to try in order — handles different naming conventions
_TABLE_CANDIDATES = [
    "Carrier Leads", "carrier leads", "Leads", "leads",
    "Carriers", "carriers", "Pipeline", "pipeline",
    "Lead Pipeline", "Carrier Pipeline",
]


def _field(fields: dict, *keys) -> str:
    for k in keys:
        v = fields.get(k) or fields.get(k.lower()) or fields.get(k.upper()) or fields.get(k.title())
        if v:
            return str(v).strip()
    return ""


@router.get("/migrate/airtable-debug")
def airtable_debug() -> dict:
    """List all tables visible in the configured Airtable base — use to diagnose 403/404."""
    s = get_settings()
    if not s.airtable_api_key or not s.airtable_base_id:
        raise HTTPException(400, "AIRTABLE_API_KEY and AIRTABLE_BASE_ID not set in Render")
    headers = {"Authorization": f"Bearer {s.airtable_api_key}"}
    try:
        # Airtable Metadata API — lists tables in base
        r = httpx.get(
            f"https://api.airtable.com/v0/meta/bases/{s.airtable_base_id}/tables",
            headers=headers,
            timeout=15,
        )
        if r.status_code == 403:
            return {
                "error": "403 Forbidden",
                "base_id": s.airtable_base_id,
                "fix": (
                    "Your Airtable token doesn't have access to this base. "
                    "Go to airtable.com/account → Personal Access Tokens → edit your token → "
                    "add scope: data.records:read AND schema.bases:read → "
                    "add this base under 'Base access'."
                ),
            }
        if r.status_code == 404:
            return {"error": "404 — base not found", "base_id": s.airtable_base_id}
        r.raise_for_status()
        tables = [t["name"] for t in r.json().get("tables", [])]
        return {"base_id": s.airtable_base_id, "tables": tables}
    except Exception as e:
        return {"error": str(e)}


@router.post("/migrate/airtable-leads")
def migrate_airtable_leads() -> dict:
    """Migrate all leads from Airtable to Supabase — auto-discovers table name."""
    s = get_settings()
    if not s.airtable_api_key or not s.airtable_base_id:
        raise HTTPException(400, "Airtable credentials not configured")

    headers = {"Authorization": f"Bearer {s.airtable_api_key}"}

    # Auto-discover the correct table name
    table_url = None
    tried = []
    for name in _TABLE_CANDIDATES:
        import urllib.parse
        url = f"https://api.airtable.com/v0/{s.airtable_base_id}/{urllib.parse.quote(name)}"
        tried.append(name)
        try:
            probe = httpx.get(url, headers=headers, params={"pageSize": 1}, timeout=10)
            if probe.status_code == 200:
                table_url = url
                break
            if probe.status_code == 403:
                raise HTTPException(
                    403,
                    f"Airtable token missing permissions. "
                    f"Go to airtable.com/account → Personal Access Tokens → edit token → "
                    f"add scope 'data.records:read' and grant access to base {s.airtable_base_id}. "
                    f"Then call GET /api/migrate/airtable-debug to see available tables."
                )
        except HTTPException:
            raise
        except Exception:
            continue

    if not table_url:
        raise HTTPException(
            404,
            f"No matching table found in base {s.airtable_base_id}. "
            f"Tried: {tried}. "
            f"Call GET /api/migrate/airtable-debug to see available table names."
        )

    # Paginate through all Airtable records
    all_records = []
    offset = None
    try:
        while True:
            params: dict = {"pageSize": 100}
            if offset:
                params["offset"] = offset
            r = httpx.get(table_url, headers=headers, params=params, timeout=30)
            r.raise_for_status()
            body = r.json()
            all_records.extend(body.get("records") or [])
            offset = body.get("offset")
            if not offset:
                break
    except httpx.HTTPStatusError as e:
        raise HTTPException(500, f"Airtable fetch error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(500, f"Connection error: {str(e)}")

    # Transform and insert
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
        equipment    = _field(fields, "Equipment", "Equipment Type", "Trailer Type")
        fleet_str    = _field(fields, "Fleet Size", "fleet_size", "Trucks", "# Trucks")

        fleet_size: int | None = None
        if fleet_str:
            try:
                fleet_size = int("".join(c for c in fleet_str if c.isdigit()) or "0") or None
            except Exception:
                pass

        if dot_number:
            existing = sb.table("leads").select("id").eq("dot_number", dot_number).limit(1).execute()
            if existing.data:
                skipped += 1
                continue
        if mc_number and not dot_number:
            existing = sb.table("leads").select("id").eq("mc_number", mc_number).limit(1).execute()
            if existing.data:
                skipped += 1
                continue

        source_ref = record.get("id", "")
        rec: dict = {
            "source":       "airtable",
            "source_ref":   source_ref,
            "company_name": company_name,
            "stage":        "new",
        }
        if phone:        rec["phone"]           = phone
        if email:        rec["email"]           = email
        if dot_number:   rec["dot_number"]      = dot_number
        if mc_number:    rec["mc_number"]       = mc_number
        if contact_name: rec["contact_name"]    = contact_name
        if fleet_size:   rec["fleet_size"]      = fleet_size
        if equipment:    rec["equipment_types"] = [equipment]

        try:
            # Check if this Airtable record was already imported (by source_ref)
            existing = sb.table("leads").select("id").eq("source_ref", source_ref).limit(1).execute()
            if existing.data:
                # Update existing row with correct column values
                lead_id = existing.data[0]["id"]
                sb.table("leads").update(rec).eq("id", lead_id).execute()
            else:
                sb.table("leads").insert(rec).execute()
            inserted += 1
        except Exception as e:
            msg = str(e)[:200]
            if not errors or msg not in errors:
                errors.append(msg)
            failed += 1

    return {
        "ok":          True,
        "table_used":  table_url.split("/")[-1],
        "fetched":     len(all_records),
        "inserted":    inserted,
        "skipped_dup": skipped,
        "failed":      failed,
        "errors":      errors[:5],
    }

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

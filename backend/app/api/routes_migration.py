"""Airtable → Supabase migration endpoints for EAGLE EYE."""
from fastapi import APIRouter, Depends, HTTPException
import httpx
from ..supabase_client import get_supabase
from ..settings import get_settings
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.post("/migrate/020-lf-dedup")
def run_020_lf_dedup() -> dict:
    """
    Migration 020 — Remove duplicate light_vehicle_drivers rows.

    Keeps the earliest record per email (then per phone), deletes the rest.
    Safe to call multiple times — subsequent runs will find nothing to delete.

    After this runs, apply the unique indexes manually in the Supabase SQL editor:
      CREATE UNIQUE INDEX IF NOT EXISTS idx_lvd_email_unique
        ON light_vehicle_drivers (email) WHERE email IS NOT NULL AND email <> '';
      CREATE UNIQUE INDEX IF NOT EXISTS idx_lvd_phone_unique
        ON light_vehicle_drivers (phone) WHERE phone IS NOT NULL AND phone <> '';
    """
    sb = get_supabase()
    rows = sb.table("light_vehicle_drivers") \
             .select("id,name,email,phone,created_at") \
             .execute().data or []

    deleted_ids: list[str] = []
    seen_emails: dict[str, str] = {}   # email → first id seen
    seen_phones: dict[str, str] = {}   # phone → first id seen

    # Sort oldest first so we keep the earliest record
    rows_sorted = sorted(rows, key=lambda r: (r.get("created_at") or "", r.get("id") or ""))

    for r in rows_sorted:
        rid = str(r.get("id") or "")
        email = (r.get("email") or "").strip().lower()
        phone = (r.get("phone") or "").strip()

        if email:
            if email in seen_emails:
                deleted_ids.append(rid)
                continue
            seen_emails[email] = rid

        if phone and rid not in deleted_ids:
            if phone in seen_phones:
                deleted_ids.append(rid)
                continue
            seen_phones[phone] = rid

    removed = []
    errors = []
    for did in deleted_ids:
        try:
            sb.table("light_vehicle_drivers").delete().eq("id", did).execute()
            removed.append(did)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{did}: {str(e)[:100]}")

    return {
        "ok": True,
        "total_before": len(rows),
        "duplicates_found": len(deleted_ids),
        "duplicates_removed": len(removed),
        "remaining": len(rows) - len(removed),
        "errors": errors,
        "next_step": (
            "Run these in Supabase SQL editor to lock in uniqueness:\n"
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_lvd_email_unique "
            "ON light_vehicle_drivers (email) WHERE email IS NOT NULL AND email <> '';\n"
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_lvd_phone_unique "
            "ON light_vehicle_drivers (phone) WHERE phone IS NOT NULL AND phone <> '';"
        ),
    }

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

        # Map Airtable field names → live leads table columns
        business_name = _field(fields, "Company Name", "company name", "Business Name",
                               "Company", "Name", "business_name") or "Unknown"
        contact_name  = _field(fields, "Contact", "Contact Name", "Owner", "contact_name")
        phone         = _field(fields, "Phone", "Phone Number", "phone number", "Mobile")
        email         = _field(fields, "Email", "Email Address", "email address")
        mc_number     = _field(fields, "MC", "MC Number", "mc_number", "MC #")
        dot_number    = _field(fields, "DOT", "DOT Number", "dot_number", "MC/DOT", "DOT #")
        equipment     = _field(fields, "Equipment", "Equipment Type", "Trailer Type",
                               "equipment_type", "Truck Type")
        city          = _field(fields, "City", "city", "Location")
        state         = _field(fields, "State", "state", "ST")
        notes         = _field(fields, "Notes", "notes", "Comments", "comment")
        fleet_str     = _field(fields, "Fleet Size", "fleet_size", "Trucks", "# Trucks",
                               "Number of Trucks")

        fleet_size: int | None = None
        if fleet_str:
            try:
                fleet_size = int("".join(c for c in fleet_str if c.isdigit()) or "0") or None
            except Exception:
                pass

        # Dedup by DOT / MC
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

        # Use actual live table column names (from information_schema query)
        rec: dict = {
            "business_name": business_name,   # col 2, NOT NULL — required
            "source":        "Airtable",      # col 13, default 'FMCSA'
            "status":        "New",           # col 14, default 'New'
        }
        if source_ref:   rec["source_ref"]    = source_ref
        if contact_name: rec["contact_name"]  = contact_name
        if phone:        rec["phone"]         = phone
        if email:        rec["email"]         = email
        if mc_number:    rec["mc_number"]     = mc_number
        if dot_number:   rec["dot_number"]    = dot_number
        if equipment:    rec["equipment_type"] = equipment   # col 10, singular
        if city:         rec["city"]          = city
        if state:        rec["state"]         = state
        if fleet_size:   rec["fleet_size"]    = fleet_size
        if notes:        rec["notes"]         = notes

        try:
            # Skip if already imported by source_ref (safe re-run)
            if source_ref:
                existing = sb.table("leads").select("id").eq("source_ref", source_ref).limit(1).execute()
                if existing.data:
                    skipped += 1
                    continue

            result = sb.table("leads").insert(rec).execute()
            if not result.data:
                raise ValueError("Insert returned no data — possible schema mismatch")
            inserted += 1
        except Exception as e:
            import ast as _ast
            err_str = str(e)
            col_msg = ""
            # supabase-py wraps PostgREST errors as a dict-like string
            # Try to parse it and extract the 'message' key (names the column)
            try:
                err_dict = _ast.literal_eval(err_str)
                col_msg = err_dict.get("message", "")
            except Exception:
                pass
            # Also try direct attribute access (postgrest-py APIError)
            if not col_msg:
                col_msg = getattr(e, "message", "") or getattr(getattr(e, "json", {}), "get", lambda k, d="": d)("message", "")

            entry = f"COLUMN ERROR: {col_msg}" if col_msg else err_str[:150]
            if not errors:
                entry += f"\nSENT KEYS: {list(rec.keys())}\nSAMPLE VALUES: source={rec.get('source')!r} stage={rec.get('stage')!r}"
            if len(errors) < 3:
                errors.append(entry)
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


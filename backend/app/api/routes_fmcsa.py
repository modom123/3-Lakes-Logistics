"""FMCSA Company Census integration — safety lookup + lead prospecting.

Dataset: FMCSA Company Census File (az4n-8mr2)
  - 4.44M rows, 147 columns, row identifier: DOT_NUMBER
  - Active, inactive, and pending entities registered with FMCSA
  - Entity data, business operations, equipment/driver data, carrier review data

Endpoints:
  GET  /api/fmcsa/safety/{dot_number}   — enrich Shield safety check
  GET  /api/fmcsa/search                — prospect search for leads
  POST /api/fmcsa/import-lead           — save found carrier as a lead
  GET  /api/fmcsa/fields                — return available filter options (debug)
"""
from __future__ import annotations

import urllib.parse
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from ..logging_service import log_agent
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])

_BASE = "https://data.transportation.gov/resource/az4n-8mr2.json"
_TIMEOUT = 20

# Core fields used in safety check
_SAFETY_SELECT = ",".join([
    "dot_number",
    "legal_name",
    "dba_name",
    "operating_status",       # AUTHORIZED, NOT AUTHORIZED, INACTIVE
    "oos_date",               # Out of service date
    "safety_rating",          # Satisfactory, Conditional, Unsatisfactory
    "safety_rating_date",
    "safety_review_date",
    "safety_review_type",
    "entity_type",            # CARRIER, BROKER, FREIGHT FORWARDER, etc.
    "carrier_operation",      # I=Interstate, A=Intrastate All, H=Intrastate HM only
    "hm_flag",                # Y/N hazmat authorized
    "pc_flag",                # Y/N passenger carrier
    "hhg_flag",               # Y/N household goods
    "total_power_units",
    "total_drivers",
    "mc_mx_ff_number",
    "phy_state",
    "phy_city",
    "telephone",
    "mcs150_form_date",       # last MCS-150 filing (activity indicator)
    "mcs150_mileage_year",
    "add_date",
])

# Full fields for prospect search
_SEARCH_SELECT = ",".join([
    "dot_number",
    "legal_name",
    "dba_name",
    "operating_status",
    "entity_type",
    "carrier_operation",
    "phy_street",
    "phy_city",
    "phy_state",
    "phy_zip",
    "telephone",
    "mc_mx_ff_number",
    "total_power_units",
    "total_drivers",
    "straight_trucks",        # straight trucks owned
    "tractor_trucks",         # tractor trucks owned
    "trailers",               # trailers owned
    "safety_rating",
    "safety_rating_date",
    "oos_date",
    "hm_flag",
    "pc_flag",
    "hhg_flag",
    "mcs150_form_date",
    "mcs150_mileage_year",
    "add_date",
    "state_carrier_id_number",
])

_UNSAFE_RATINGS = {"Unsatisfactory", "Conditional"}


def _fetch(params: dict) -> list[dict[str, Any]]:
    params.setdefault("$limit", 100)
    try:
        r = httpx.get(_BASE, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json() or []
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"FMCSA API error: {e.response.status_code} — {e.response.text[:200]}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"FMCSA connection error: {str(e)}")


def _int(val: Any, default: int = 0) -> int:
    try:
        return int(str(val).replace(",", "")) if val else default
    except (ValueError, TypeError):
        return default


def _normalize(rec: dict) -> dict:
    """Normalize raw FMCSA census record to a clean internal shape."""
    rating = (rec.get("safety_rating") or "Not Rated").strip()
    oos = rec.get("oos_date")
    op_status = (rec.get("operating_status") or "").strip().upper()
    mc_raw = rec.get("mc_mx_ff_number") or ""
    mc_clean = mc_raw.replace("MC-", "").replace("MX-", "").replace("FF-", "").strip()

    # Derive safety light
    safety_light = "green"
    if op_status == "NOT AUTHORIZED" or oos:
        safety_light = "red"
    elif rating == "Unsatisfactory":
        safety_light = "red"
    elif rating == "Conditional" or op_status not in ("AUTHORIZED", ""):
        safety_light = "yellow"

    # Equipment breakdown
    straight = _int(rec.get("straight_trucks"))
    tractors = _int(rec.get("tractor_trucks"))
    trailers = _int(rec.get("trailers"))
    total_units = _int(rec.get("total_power_units")) or (straight + tractors)

    # Determine primary equipment type from what they operate
    equip_types = []
    if tractors > 0:
        equip_types.append("Tractor-Trailer")
    if straight > 0:
        equip_types.append("Straight Truck")
    if rec.get("hm_flag") == "Y":
        equip_types.append("Hazmat")
    if rec.get("pc_flag") == "Y":
        equip_types.append("Passenger")

    # MCS-150 age (activity indicator — older = less active)
    mcs150 = (rec.get("mcs150_form_date") or "")[:10]

    return {
        "dot_number":        str(rec.get("dot_number") or "").strip(),
        "mc_number":         mc_clean,
        "legal_name":        (rec.get("legal_name") or "").strip(),
        "dba_name":          (rec.get("dba_name") or "").strip(),
        "operating_status":  op_status,
        "entity_type":       (rec.get("entity_type") or "").strip(),
        "carrier_operation": (rec.get("carrier_operation") or "").strip(),
        "phone":             (rec.get("telephone") or "").strip(),
        "street":            (rec.get("phy_street") or "").strip(),
        "city":              (rec.get("phy_city") or "").strip(),
        "state":             (rec.get("phy_state") or "").strip(),
        "zip":               (rec.get("phy_zip") or "").strip(),
        "total_power_units": total_units,
        "straight_trucks":   straight,
        "tractor_trucks":    tractors,
        "trailers":          trailers,
        "total_drivers":     _int(rec.get("total_drivers")),
        "equipment_types":   equip_types,
        "safety_rating":     rating,
        "safety_rating_date":(rec.get("safety_rating_date") or "")[:10],
        "safety_review_date":(rec.get("safety_review_date") or "")[:10],
        "oos_date":          oos,
        "hm_flag":           rec.get("hm_flag") == "Y",
        "pc_flag":           rec.get("pc_flag") == "Y",
        "hhg_flag":          rec.get("hhg_flag") == "Y",
        "mcs150_date":       mcs150,
        "mcs150_year":       rec.get("mcs150_mileage_year") or "",
        "add_date":          (rec.get("add_date") or "")[:10],
        "safety_light":      safety_light,
    }


# ── Safety lookup ─────────────────────────────────────────────────────────────

@router.get("/safety/{dot_number}")
def fmcsa_safety(dot_number: str) -> dict:
    """Look up full carrier safety + census data by DOT number."""
    records = _fetch({
        "$where": f"dot_number='{dot_number.strip()}'",
        "$select": _SAFETY_SELECT,
        "$limit": 1,
    })
    if not records:
        return {"found": False, "dot_number": dot_number}
    carrier = _normalize(records[0])
    log_agent("shield", "fmcsa_census_lookup",
              payload={"dot": dot_number, "light": carrier["safety_light"],
                       "rating": carrier["safety_rating"], "status": carrier["operating_status"]})
    return {"found": True, **carrier}


# ── Prospect search ───────────────────────────────────────────────────────────

@router.get("/search")
def fmcsa_search(
    state: str | None = Query(default=None, description="2-letter state, e.g. IL"),
    city: str | None = Query(default=None),
    company_name: str | None = Query(default=None, description="Partial company / DBA name search"),
    min_trucks: int = Query(default=1, ge=1),
    max_trucks: int = Query(default=30, le=500),
    carrier_op: str | None = Query(default=None, description="I=interstate, A=intrastate, H=intrastate HM"),
    entity_type: str | None = Query(default="CARRIER", description="CARRIER, BROKER, etc."),
    hazmat: bool | None = Query(default=None, description="Filter to hazmat-authorized carriers"),
    authorized_only: bool = Query(default=True, description="Only AUTHORIZED operating status"),
    min_drivers: int = Query(default=0, ge=0),
    tractor_only: bool = Query(default=False, description="Only carriers with tractor trucks"),
    phone_required: bool = Query(default=False, description="Only return records with a phone number"),
    limit: int = Query(default=50, le=200),
) -> dict:
    """Search FMCSA census — 4.44M carriers, 147 fields."""
    if not state and not company_name:
        raise HTTPException(400, "Provide at least a state (2-letter) or a company name to search.")

    conditions: list[str] = []

    if authorized_only:
        conditions.append("operating_status='AUTHORIZED'")
    # Only carriers (exclude brokers/freight forwarders unless overridden)
    if entity_type:
        conditions.append(f"entity_type='{entity_type.upper()}'")
    if state:
        conditions.append(f"phy_state='{state.upper().strip()}'")
    if city:
        safe_city = city.upper().replace("'", "''")
        conditions.append(f"upper(phy_city) like '%25{urllib.parse.quote(safe_city)}%25'")
    if company_name:
        safe_name = company_name.upper().replace("'", "''")
        quoted = urllib.parse.quote(safe_name)
        conditions.append(
            f"(upper(legal_name) like '%25{quoted}%25' OR upper(dba_name) like '%25{quoted}%25')"
        )
    if carrier_op:
        conditions.append(f"carrier_operation='{carrier_op.upper()}'")
    if hazmat is True:
        conditions.append("hm_flag='Y'")
    elif hazmat is False:
        conditions.append("hm_flag='N'")
    if tractor_only:
        conditions.append("tractor_trucks > '0'")
    if phone_required:
        conditions.append("telephone IS NOT NULL")
    # Active carriers — exclude those with OOS date
    conditions.append("oos_date IS NULL")
    # Fleet size range
    if min_trucks > 1:
        conditions.append(f"total_power_units >= '{min_trucks}'")
    if max_trucks < 500:
        conditions.append(f"total_power_units <= '{max_trucks}'")
    if min_drivers > 0:
        conditions.append(f"total_drivers >= '{min_drivers}'")

    where = " AND ".join(conditions)

    records = _fetch({
        "$where": where,
        "$select": _SEARCH_SELECT,
        "$limit": limit,
        "$order": "total_power_units DESC",
    })

    normalized = [_normalize(r) for r in records]

    # Mark already-imported leads by DOT
    sb = get_supabase()
    existing_dots: set[str] = set()
    dots = [r["dot_number"] for r in normalized if r["dot_number"]]
    if dots:
        existing = sb.table("leads").select("dot_number").in_("dot_number", dots[:100]).execute()
        existing_dots = {str(r["dot_number"]) for r in (existing.data or [])}

    for r in normalized:
        r["already_lead"] = r["dot_number"] in existing_dots

    return {
        "count":   len(normalized),
        "results": normalized,
        "filters": {
            "state": state, "city": city,
            "min_trucks": min_trucks, "max_trucks": max_trucks,
            "carrier_op": carrier_op, "authorized_only": authorized_only,
        },
    }


# ── Import a carrier as a lead ─────────────────────────────────────────────────

@router.post("/import-lead")
def fmcsa_import_lead(data: dict) -> dict:
    """Save an FMCSA-found carrier to the leads table."""
    dot  = (data.get("dot_number") or "").strip()
    name = (data.get("legal_name") or data.get("dba_name") or "").strip()
    if not name:
        raise HTTPException(400, "legal_name required")

    sb = get_supabase()
    # Dedup by DOT
    if dot:
        existing = sb.table("leads").select("id").eq("dot_number", dot).limit(1).execute()
        if existing.data:
            return {"ok": False, "reason": "already_exists", "dot_number": dot}

    equip = data.get("equipment_types") or []
    notes_parts = [f"FMCSA Safety Rating: {data.get('safety_rating','Not Rated')}"]
    if data.get("tractor_trucks"):
        notes_parts.append(f"Tractors: {data['tractor_trucks']}")
    if data.get("straight_trucks"):
        notes_parts.append(f"Straight trucks: {data['straight_trucks']}")
    if data.get("total_drivers"):
        notes_parts.append(f"Drivers: {data['total_drivers']}")
    if data.get("carrier_operation"):
        op = {"I": "Interstate", "A": "Intrastate (all)", "H": "Intrastate HM"}.get(
            data["carrier_operation"], data["carrier_operation"]
        )
        notes_parts.append(f"Operation: {op}")
    if data.get("mcs150_date"):
        notes_parts.append(f"MCS-150 filed: {data['mcs150_date']}")

    rec: dict[str, Any] = {
        "business_name": name,
        "source":        "FMCSA",
        "status":        "New",
        "notes":         " · ".join(notes_parts),
    }
    if dot:                                  rec["dot_number"]     = dot
    if data.get("mc_number"):                rec["mc_number"]      = data["mc_number"]
    if data.get("phone"):                    rec["phone"]          = data["phone"]
    if data.get("city"):                     rec["city"]           = data["city"]
    if data.get("state"):                    rec["state"]          = data["state"]
    if data.get("total_power_units"):        rec["fleet_size"]     = int(data["total_power_units"])
    if equip:                                rec["equipment_type"] = equip[0]

    result = sb.table("leads").insert(rec).execute()
    if not result.data:
        raise HTTPException(500, "Insert failed")

    log_agent("scout", "fmcsa_import", payload={"dot": dot, "name": name,
              "fleet": data.get("total_power_units"), "state": data.get("state")})
    return {"ok": True, "lead": result.data[0]}


# ── Debug: available filter values ────────────────────────────────────────────

@router.get("/fields")
def fmcsa_fields() -> dict:
    """Return sample values for key filter fields — useful for UI dropdowns."""
    return {
        "carrier_operation": {
            "I": "Interstate",
            "A": "Intrastate (all commodities)",
            "H": "Intrastate hazmat only",
        },
        "entity_type": ["CARRIER", "BROKER", "FREIGHT FORWARDER", "CARGO TANK MANUFACTURER",
                        "IEP", "MEXICAN CARRIER"],
        "operating_status": ["AUTHORIZED", "NOT AUTHORIZED", "INACTIVE", "PENDING APPLICATION"],
        "safety_rating": ["Satisfactory", "Conditional", "Unsatisfactory", "Not Rated"],
        "dataset": {
            "rows": "4.44M",
            "columns": 147,
            "identifier": "DOT_NUMBER",
            "api": "https://data.transportation.gov/resource/az4n-8mr2.json",
        },
    }

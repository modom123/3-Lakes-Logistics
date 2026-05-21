"""FMCSA open-data integration — safety lookup + lead prospecting.

Dataset: Motor Carrier Census (az4n-8mr2)
API:     https://data.transportation.gov/api/v3/views/az4n-8mr2/query.json
         also: https://data.transportation.gov/resource/az4n-8mr2.json  (Socrata REST)

Two uses:
  GET /api/fmcsa/safety/{dot_number}   — enrich Shield safety check with census data
  GET /api/fmcsa/search                — prospect search for lead generation
  POST /api/fmcsa/import-lead          — save a found carrier as a lead
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

# Socrata REST endpoint (simpler, supports $where/$select/$limit SoQL)
_BASE = "https://data.transportation.gov/resource/az4n-8mr2.json"
_TIMEOUT = 15

# Fields we care about from the census dataset
_SELECT = ",".join([
    "dot_number",
    "legal_name",
    "dba_name",
    "phy_street",
    "phy_city",
    "phy_state",
    "phy_zip",
    "telephone",
    "mc_mx_ff_number",
    "total_power_units",
    "drivers",
    "carrier_operation",  # I=interstate, A=intrastate all, H=intrastate HM
    "safety_rating",
    "safety_rating_date",
    "oos_date",
    "entity_type",
    "add_date",
    "mcs150_form_date",
])

# Safety ratings considered acceptable
_SAFE_RATINGS = {"Satisfactory", "None"}  # "None" = not yet rated (still operating)
_UNSAFE_RATINGS = {"Unsatisfactory", "Conditional"}


def _fetch(params: dict) -> list[dict[str, Any]]:
    params.setdefault("$select", _SELECT)
    params.setdefault("$limit", 100)
    try:
        r = httpx.get(_BASE, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json() or []
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"FMCSA API error: {e.response.status_code}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"FMCSA connection error: {str(e)}")


def _normalize(rec: dict) -> dict:
    """Normalize raw FMCSA record to our internal shape."""
    units = rec.get("total_power_units") or "0"
    try:
        fleet = int(str(units).replace(",", ""))
    except ValueError:
        fleet = 0

    rating = (rec.get("safety_rating") or "None").strip()
    oos = rec.get("oos_date")

    safety_light = "green"
    if rating in _UNSAFE_RATINGS:
        safety_light = "red"
    elif oos:
        safety_light = "red"
    elif rating == "Conditional":
        safety_light = "yellow"

    mc_raw = rec.get("mc_mx_ff_number") or ""
    mc_clean = mc_raw.replace("MC-", "").replace("MX-", "").strip() if mc_raw else ""

    return {
        "dot_number":        str(rec.get("dot_number") or "").strip(),
        "mc_number":         mc_clean,
        "legal_name":        (rec.get("legal_name") or "").strip(),
        "dba_name":          (rec.get("dba_name") or "").strip(),
        "phone":             (rec.get("telephone") or "").strip(),
        "street":            (rec.get("phy_street") or "").strip(),
        "city":              (rec.get("phy_city") or "").strip(),
        "state":             (rec.get("phy_state") or "").strip(),
        "zip":               (rec.get("phy_zip") or "").strip(),
        "fleet_size":        fleet,
        "carrier_operation": (rec.get("carrier_operation") or "").strip(),
        "safety_rating":     rating,
        "safety_rating_date":(rec.get("safety_rating_date") or "")[:10],
        "oos_date":          oos,
        "entity_type":       (rec.get("entity_type") or "").strip(),
        "mcs150_date":       (rec.get("mcs150_form_date") or "")[:10],
        "safety_light":      safety_light,
    }


# ── Safety lookup ─────────────────────────────────────────────────────────────

@router.get("/safety/{dot_number}")
def fmcsa_safety(dot_number: str) -> dict:
    """Look up carrier safety data by DOT number from the FMCSA census."""
    records = _fetch({"$where": f"dot_number='{dot_number.strip()}'"})
    if not records:
        return {"found": False, "dot_number": dot_number}
    carrier = _normalize(records[0])
    log_agent("shield", "fmcsa_lookup", payload={"dot": dot_number, "light": carrier["safety_light"]})
    return {"found": True, **carrier}


# ── Lead prospecting search ───────────────────────────────────────────────────

@router.get("/search")
def fmcsa_search(
    state: str | None = Query(default=None, description="2-letter state code, e.g. IL"),
    city: str | None = Query(default=None),
    min_trucks: int = Query(default=1),
    max_trucks: int = Query(default=50, description="Cap to avoid mega-fleets"),
    carrier_op: str | None = Query(default=None, description="I=interstate, A=intrastate"),
    limit: int = Query(default=50, le=200),
) -> dict:
    """Search FMCSA census for carriers to prospect as leads."""
    conditions = []

    if state:
        conditions.append(f"phy_state='{state.upper()}'")
    if city:
        conditions.append(f"upper(phy_city) like '%25{urllib.parse.quote(city.upper())}%25'")
    if carrier_op:
        conditions.append(f"carrier_operation='{carrier_op.upper()}'")

    # Only active carriers (no OOS date, not inactive)
    conditions.append("oos_date IS NULL")

    # Fleet size filter — only carriers with trucks recorded
    if min_trucks > 1:
        conditions.append(f"total_power_units >= '{min_trucks}'")
    if max_trucks < 9999:
        conditions.append(f"total_power_units <= '{max_trucks}'")

    where = " AND ".join(conditions) if conditions else "oos_date IS NULL"

    records = _fetch({
        "$where": where,
        "$limit": limit,
        "$order": "total_power_units DESC",
        "$select": _SELECT,
    })

    normalized = [_normalize(r) for r in records]

    # Dedup against existing leads by DOT number
    sb = get_supabase()
    existing_dots = set()
    if normalized:
        dots = [r["dot_number"] for r in normalized if r["dot_number"]]
        if dots:
            existing = sb.table("leads").select("dot_number").in_("dot_number", dots).execute()
            existing_dots = {r["dot_number"] for r in (existing.data or [])}

    for r in normalized:
        r["already_lead"] = r["dot_number"] in existing_dots

    return {
        "count": len(normalized),
        "results": normalized,
        "filters": {"state": state, "city": city, "min_trucks": min_trucks, "max_trucks": max_trucks},
    }


# ── Import a found carrier as a lead ─────────────────────────────────────────

@router.post("/import-lead")
def fmcsa_import_lead(data: dict) -> dict:
    """Save an FMCSA-found carrier directly into the leads table."""
    dot = (data.get("dot_number") or "").strip()
    name = (data.get("legal_name") or data.get("dba_name") or "Unknown").strip()

    if not name:
        raise HTTPException(400, "legal_name required")

    sb = get_supabase()

    # Dedup check
    if dot:
        existing = sb.table("leads").select("id").eq("dot_number", dot).limit(1).execute()
        if existing.data:
            return {"ok": False, "reason": "already_exists", "dot_number": dot}

    rec = {
        "business_name": name,
        "source":        "FMCSA",
        "status":        "New",
    }
    if dot:                             rec["dot_number"]    = dot
    if data.get("mc_number"):           rec["mc_number"]     = data["mc_number"]
    if data.get("phone"):               rec["phone"]         = data["phone"]
    if data.get("city"):                rec["city"]          = data["city"]
    if data.get("state"):               rec["state"]         = data["state"]
    if data.get("fleet_size"):          rec["fleet_size"]    = int(data["fleet_size"])
    if data.get("safety_rating"):       rec["notes"]         = f"FMCSA Safety Rating: {data['safety_rating']}"

    result = sb.table("leads").insert(rec).execute()
    if not result.data:
        raise HTTPException(500, "Insert failed")

    log_agent("scout", "fmcsa_import", payload={"dot": dot, "name": name})
    return {"ok": True, "lead": result.data[0]}

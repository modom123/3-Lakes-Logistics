"""Scout — BOL/rate-con OCR verification + FMCSA daily lead prospecting."""
from __future__ import annotations

import urllib.parse
from typing import Any

import httpx

from ..logging_service import log_agent
from ..supabase_client import get_supabase

_FMCSA_BASE = "https://data.transportation.gov/resource/az4n-8mr2.json"
_FMCSA_TIMEOUT = 25

# ── OCR / document verification (Steps 27-28) ────────────────────────────────

def ocr_document(image_url_or_bytes: Any) -> dict[str, Any]:
    """Step 27: call Google Vision on a BOL/Rate Con. Stub returns schema."""
    # TODO: google-cloud-vision ImageAnnotatorClient.document_text_detection
    return {
        "origin": None, "destination": None, "rate_total": None,
        "commodity": None, "weight_lbs": None, "broker_mc": None,
        "pickup_at": None, "delivery_at": None, "refs": [],
    }


def verify(extracted: dict[str, Any], expected_broker: str | None = None) -> dict[str, Any]:
    """Step 28: compare OCR against the booked load."""
    issues: list[str] = []
    if expected_broker and extracted.get("broker_mc") and expected_broker != extracted["broker_mc"]:
        issues.append("broker_mc_mismatch")
    if not extracted.get("rate_total"):
        issues.append("rate_not_detected")
    return {"ok": not issues, "issues": issues}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    log_agent("scout", "ocr", payload={"file": payload.get("file_ref")}, result="stub")
    return {"agent": "scout", "status": "stub", "extracted": ocr_document(None)}


# ── FMCSA daily prospecting ───────────────────────────────────────────────────

# 3 daily search profiles targeting 3 Lakes' ideal carrier market
DAILY_SEARCH_PROFILES: list[dict[str, Any]] = [
    {
        "name": "midwest_small_interstate",
        "label": "Midwest Small Interstate Fleets",
        "description": "1-5 truck interstate carriers in IL/WI/MN/IN/OH — core 3 Lakes territory",
        "params": {
            "operating_status": "AUTHORIZED",
            "entity_type": "CARRIER",
            "carrier_operation": "I",
            "phy_state": ["IL", "WI", "MN", "IN", "OH"],
            "min_trucks": 1,
            "max_trucks": 5,
            "tractor_only": True,
        },
    },
    {
        "name": "midwest_mid_dryvab",
        "label": "Midwest Mid-Size Dry Van / Flatbed",
        "description": "2-10 truck authorized carriers in broader midwest — growth prospects",
        "params": {
            "operating_status": "AUTHORIZED",
            "entity_type": "CARRIER",
            "phy_state": ["IL", "WI", "MN", "IN", "OH", "IA", "MO", "MI", "KY"],
            "min_trucks": 2,
            "max_trucks": 10,
            "tractor_only": False,
        },
    },
    {
        "name": "new_entrants_nationwide",
        "label": "New Carrier Entrants",
        "description": "Recently registered carriers 1-3 trucks — catch them before competition does",
        "params": {
            "operating_status": "AUTHORIZED",
            "entity_type": "CARRIER",
            "min_trucks": 1,
            "max_trucks": 3,
            "order_by": "add_date DESC",
        },
    },
]

_SEARCH_SELECT = ",".join([
    "dot_number", "legal_name", "dba_name", "operating_status",
    "entity_type", "carrier_operation",
    "phy_street", "phy_city", "phy_state", "phy_zip",
    "telephone", "mc_mx_ff_number",
    "total_power_units", "total_drivers",
    "straight_trucks", "tractor_trucks", "trailers",
    "safety_rating", "oos_date",
    "hm_flag", "pc_flag", "hhg_flag",
    "mcs150_form_date", "mcs150_mileage_year", "add_date",
])


def _fmcsa_fetch(conditions: list[str], order_by: str = "total_power_units DESC",
                 limit: int = 50) -> list[dict]:
    where = " AND ".join(conditions) if conditions else "operating_status='AUTHORIZED'"
    params: dict[str, Any] = {
        "$where":  where,
        "$select": _SEARCH_SELECT,
        "$limit":  limit,
        "$order":  order_by,
    }
    try:
        r = httpx.get(_FMCSA_BASE, params=params, timeout=_FMCSA_TIMEOUT)
        r.raise_for_status()
        return r.json() or []
    except Exception as e:  # noqa: BLE001
        log_agent("scout", "fmcsa_fetch_error", error=str(e))
        return []


def _int(val: Any, default: int = 0) -> int:
    try:
        return int(str(val).replace(",", "")) if val else default
    except (ValueError, TypeError):
        return default


def _normalize(rec: dict) -> dict:
    mc_raw = rec.get("mc_mx_ff_number") or ""
    mc_clean = mc_raw.replace("MC-", "").replace("MX-", "").replace("FF-", "").strip()
    straight  = _int(rec.get("straight_trucks"))
    tractors  = _int(rec.get("tractor_trucks"))
    total     = _int(rec.get("total_power_units")) or (straight + tractors)
    equip_types = []
    if tractors > 0: equip_types.append("Tractor-Trailer")
    if straight > 0: equip_types.append("Straight Truck")
    if rec.get("hm_flag") == "Y": equip_types.append("Hazmat")
    rating = (rec.get("safety_rating") or "Not Rated").strip()
    return {
        "dot_number":       str(rec.get("dot_number") or "").strip(),
        "mc_number":        mc_clean,
        "legal_name":       (rec.get("legal_name") or "").strip(),
        "dba_name":         (rec.get("dba_name") or "").strip(),
        "operating_status": (rec.get("operating_status") or "").strip().upper(),
        "entity_type":      (rec.get("entity_type") or "").strip(),
        "carrier_operation":(rec.get("carrier_operation") or "").strip(),
        "phone":            (rec.get("telephone") or "").strip(),
        "city":             (rec.get("phy_city") or "").strip(),
        "state":            (rec.get("phy_state") or "").strip(),
        "total_power_units":total,
        "tractor_trucks":   tractors,
        "straight_trucks":  straight,
        "total_drivers":    _int(rec.get("total_drivers")),
        "equipment_types":  equip_types,
        "safety_rating":    rating,
        "oos_date":         rec.get("oos_date"),
        "mcs150_date":      (rec.get("mcs150_form_date") or "")[:10],
        "add_date":         (rec.get("add_date") or "")[:10],
    }


def _build_conditions(params: dict[str, Any]) -> list[str]:
    """Convert a profile params dict to SoQL conditions list."""
    conds: list[str] = []
    op_status = params.get("operating_status", "AUTHORIZED")
    conds.append(f"operating_status='{op_status}'")

    entity = params.get("entity_type")
    if entity:
        conds.append(f"entity_type='{entity.upper()}'")

    carrier_op = params.get("carrier_operation")
    if carrier_op:
        conds.append(f"carrier_operation='{carrier_op.upper()}'")

    # Multi-state: build OR clause
    states = params.get("phy_state")
    if states:
        if isinstance(states, list):
            quoted = ",".join(f"'{s}'" for s in states)
            conds.append(f"phy_state in({quoted})")
        else:
            conds.append(f"phy_state='{states}'")

    min_trucks = params.get("min_trucks", 1)
    max_trucks = params.get("max_trucks")
    if min_trucks and min_trucks > 1:
        conds.append(f"total_power_units >= '{min_trucks}'")
    if max_trucks:
        conds.append(f"total_power_units <= '{max_trucks}'")

    if params.get("tractor_only"):
        conds.append("tractor_trucks > '0'")

    # Exclude OOS carriers
    conds.append("oos_date IS NULL")

    return conds


def _import_record(rec: dict, profile_name: str) -> bool:
    """Insert a normalized carrier record into leads if not already present. Returns True if new."""
    dot  = rec["dot_number"]
    name = rec["legal_name"] or rec["dba_name"]
    if not name:
        return False

    sb = get_supabase()

    # Dedup by DOT
    if dot:
        existing = sb.table("leads").select("id").eq("dot_number", dot).limit(1).execute()
        if existing.data:
            return False

    # Also dedup by name if no DOT
    if not dot:
        existing = sb.table("leads").select("id").eq("business_name", name).limit(1).execute()
        if existing.data:
            return False

    notes_parts = [f"FMCSA Safety Rating: {rec['safety_rating']}"]
    if rec.get("tractor_trucks"):
        notes_parts.append(f"Tractors: {rec['tractor_trucks']}")
    if rec.get("straight_trucks"):
        notes_parts.append(f"Straight trucks: {rec['straight_trucks']}")
    if rec.get("total_drivers"):
        notes_parts.append(f"Drivers: {rec['total_drivers']}")
    if rec.get("carrier_operation"):
        op_label = {"I": "Interstate", "A": "Intrastate (all)", "H": "Intrastate HM"}.get(
            rec["carrier_operation"], rec["carrier_operation"])
        notes_parts.append(f"Operation: {op_label}")
    if rec.get("mcs150_date"):
        notes_parts.append(f"MCS-150 filed: {rec['mcs150_date']}")
    notes_parts.append(f"Scout profile: {profile_name}")

    row: dict[str, Any] = {
        "business_name": name,
        "source":        "FMCSA",
        "status":        "New",
        "notes":         " · ".join(notes_parts),
    }
    if dot:                               row["dot_number"]     = dot
    if rec.get("mc_number"):              row["mc_number"]      = rec["mc_number"]
    if rec.get("phone"):                  row["phone"]          = rec["phone"]
    if rec.get("city"):                   row["city"]           = rec["city"]
    if rec.get("state"):                  row["state"]          = rec["state"]
    if rec.get("total_power_units"):      row["fleet_size"]     = int(rec["total_power_units"])
    equip = rec.get("equipment_types") or []
    if equip:                             row["equipment_type"] = equip[0]

    try:
        result = sb.table("leads").insert(row).execute()
        return bool(result.data)
    except Exception as e:  # noqa: BLE001
        log_agent("scout", "import_error", error=str(e), payload={"dot": dot, "name": name})
        return False


def prospect_fmcsa(profile: dict[str, Any]) -> dict[str, Any]:
    """Run a single FMCSA search profile and auto-import new leads.

    Called by APScheduler — one call per profile per day.
    """
    name  = profile.get("name", "unnamed")
    label = profile.get("label", name)
    params = profile.get("params", {})

    log_agent("scout", "prospect_start", payload={"profile": name, "label": label})

    conditions = _build_conditions(params)
    order_by   = params.get("order_by", "total_power_units DESC")
    records    = _fmcsa_fetch(conditions, order_by=order_by, limit=60)

    normalized  = [_normalize(r) for r in records]
    imported    = 0
    skipped     = 0

    for rec in normalized:
        if _import_record(rec, name):
            imported += 1
        else:
            skipped += 1

    log_agent("scout", "prospect_done", payload={
        "profile":  name,
        "fetched":  len(normalized),
        "imported": imported,
        "skipped":  skipped,
    })

    return {
        "profile":  name,
        "label":    label,
        "fetched":  len(normalized),
        "imported": imported,
        "skipped":  skipped,
    }


def run_daily_prospecting() -> dict[str, Any]:
    """Run all 3 daily FMCSA search profiles. Called by APScheduler at 07:00 UTC."""
    results = []
    total_imported = 0
    for profile in DAILY_SEARCH_PROFILES:
        r = prospect_fmcsa(profile)
        results.append(r)
        total_imported += r["imported"]

    log_agent("scout", "daily_prospecting_complete", payload={
        "profiles_run": len(results),
        "total_imported": total_imported,
    })
    return {"profiles_run": len(results), "total_imported": total_imported, "results": results}

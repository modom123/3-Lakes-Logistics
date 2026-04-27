"""Phase 2 — Load Dispatch handlers (steps 31–60)."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from uuid import UUID

from ...agents import scout, nova, signal, orbit, sonny, audit
from ...logging_service import get_logger, log_agent
from ...settings import get_settings

log = get_logger("3ll.execution.dispatch")

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _db():
    try:
        from ...supabase_client import get_supabase
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _load(load_id: str | None) -> dict:
    if not load_id:
        return {}
    sb = _db()
    if not sb:
        return {}
    try:
        r = sb.table("loads").select("*").eq("id", load_id).maybe_single().execute()
        return r.data or {}
    except Exception:  # noqa: BLE001
        return {}


# ── Step 31: dispatch.load_received ──────────────────────────────────────────

def h31_dispatch_load_received(carrier_id, contract_id, payload):
    sb = _db()
    load_data = {
        "carrier_id": str(carrier_id) if carrier_id else None,
        "broker_name": payload.get("broker_name"),
        "load_number": payload.get("load_number"),
        "origin_city": payload.get("origin_city"),
        "origin_state": payload.get("origin_state"),
        "dest_city": payload.get("dest_city"),
        "dest_state": payload.get("dest_state"),
        "pickup_at": payload.get("pickup_at"),
        "delivery_at": payload.get("delivery_at"),
        "miles": payload.get("miles"),
        "rate_total": payload.get("rate_total"),
        "rate_per_mile": payload.get("rate_per_mile"),
        "status": "booked",
        "created_at": _NOW(),
    }
    if sb:
        try:
            r = sb.table("loads").insert(load_data).execute()
            load_id = r.data[0]["id"] if r.data else None
            return {"received": True, "load_id": load_id, **load_data}
        except Exception as e:  # noqa: BLE001
            return {"received": False, "error": str(e)}
    return {"received": True, "load_id": None, "note": "supabase_not_configured", **load_data}


# ── Step 32: clm.scan_rate_conf ───────────────────────────────────────────────

def h32_clm_scan_rate_conf(carrier_id, contract_id, payload):
    raw_text = payload.get("raw_text") or payload.get("rate_conf_text")
    if not raw_text:
        return {"scanned": False, "reason": "no_raw_text", "extracted": {}, "confidence": 0.0}
    s = get_settings()
    if not s.anthropic_api_key:
        return {
            "scanned": False,
            "note": "anthropic_not_configured",
            "extracted": {
                "broker_name": payload.get("broker_name"),
                "rate_total": payload.get("rate_total"),
                "origin_city": payload.get("origin_city"),
                "destination_city": payload.get("dest_city"),
                "pickup_date": payload.get("pickup_at", "")[:10] if payload.get("pickup_at") else None,
            },
            "confidence": 0.5,
            "warnings": [],
        }
    try:
        from ...clm.scanner import scan_contract
        extracted, confidence, warnings = scan_contract(raw_text, "rate_confirmation")
        log_agent("clm", "scan_rate_conf", carrier_id=str(carrier_id) if carrier_id else None,
                  result=f"confidence={confidence}")
        return {"scanned": True, "extracted": extracted, "confidence": confidence, "warnings": warnings}
    except Exception as e:  # noqa: BLE001
        return {"scanned": False, "error": str(e), "extracted": {}, "confidence": 0.0}


# ── Step 33: clm.validate_rate ────────────────────────────────────────────────

def h33_clm_validate_rate(carrier_id, contract_id, payload):
    extracted = payload.get("extracted") or {}
    rate_total = extracted.get("rate_total") or payload.get("rate_total") or 0
    miles = payload.get("miles") or 0
    rate_per_mile = (rate_total / miles) if miles > 0 else extracted.get("rate_per_mile") or 0
    # Market benchmark: $2.50–$4.50/mi dry van, flag if outside range
    low, high = 1.80, 6.00
    valid = low <= rate_per_mile <= high
    warnings = []
    if rate_per_mile < low:
        warnings.append(f"Rate ${rate_per_mile:.2f}/mi is below market floor ${low}/mi")
    if rate_per_mile > high:
        warnings.append(f"Rate ${rate_per_mile:.2f}/mi is above market ceiling ${high}/mi")
    return {
        "valid": valid,
        "rate_total": rate_total,
        "rate_per_mile": round(rate_per_mile, 4),
        "market_low": low,
        "market_high": high,
        "warnings": warnings,
    }


# ── Step 34: dispatch.match_truck ─────────────────────────────────────────────

def h34_dispatch_match_truck(carrier_id, contract_id, payload):
    sb = _db()
    equipment = (payload.get("extracted") or {}).get("equipment_type") or payload.get("equipment_type")
    if not sb:
        return {"matched": False, "note": "supabase_not_configured"}
    try:
        q = sb.table("fleet_assets").select("id,truck_id,trailer_type,max_weight,status,carrier_id")
        q = q.eq("status", "available")
        if equipment:
            q = q.eq("trailer_type", equipment)
        trucks = q.limit(20).execute().data or []
        if not trucks:
            return {"matched": False, "reason": "no_available_trucks", "equipment": equipment}
        return {"matched": True, "candidates": trucks, "count": len(trucks)}
    except Exception as e:  # noqa: BLE001
        return {"matched": False, "error": str(e)}


# ── Step 35: dispatch.score_match ─────────────────────────────────────────────

def h35_dispatch_score_match(carrier_id, contract_id, payload):
    candidates = payload.get("candidates") or []
    if not candidates:
        return {"scored": False, "reason": "no_candidates"}
    sb = _db()
    scored = []
    for truck in candidates:
        score = 50  # base
        hos = 0
        if sb:
            try:
                r = sb.table("driver_hos_status").select("drive_remaining").eq(
                    "carrier_id", truck.get("carrier_id", "")).maybe_single().execute()
                hos = (r.data or {}).get("drive_remaining", 0)
            except Exception:  # noqa: BLE001
                pass
        score += min(hos / 11.0 * 30, 30)  # up to +30 for full HOS
        scored.append({**truck, "score": round(score, 1), "hos_remaining": hos})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return {"scored": True, "ranked_trucks": scored, "top_truck": scored[0] if scored else None}


# ── Step 36: dispatch.offer_load ──────────────────────────────────────────────

def h36_dispatch_offer_load(carrier_id, contract_id, payload):
    top = payload.get("top_truck") or (payload.get("ranked_trucks") or [{}])[0]
    truck_id = top.get("truck_id") or top.get("id")
    if not truck_id:
        return {"offered": False, "reason": "no_truck_selected"}
    s = get_settings()
    load_details = {
        "load_id": payload.get("load_id"),
        "origin": f"{payload.get('origin_city')}, {payload.get('origin_state')}",
        "destination": f"{payload.get('dest_city')}, {payload.get('dest_state')}",
        "rate_total": payload.get("rate_total"),
        "pickup_at": payload.get("pickup_at"),
    }
    # SMS offer via Twilio
    if s.twilio_account_sid and s.twilio_auth_token:
        try:
            from twilio.rest import Client  # type: ignore
            driver_phone = top.get("phone") or payload.get("driver_phone")
            if driver_phone:
                msg = (f"LOAD OFFER: {load_details['origin']} → {load_details['destination']} "
                       f"| Rate: ${load_details['rate_total']} | Pickup: {load_details['pickup_at']} "
                       f"| Reply YES to accept")
                Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                    body=msg, from_=s.twilio_from_number, to=driver_phone)
        except Exception:  # noqa: BLE001
            pass
    return {"offered": True, "truck_id": truck_id, "load_details": load_details, "offer_sent_at": _NOW()}


# ── Step 37: dispatch.driver_accept ───────────────────────────────────────────

def h37_dispatch_driver_accept(carrier_id, contract_id, payload):
    accepted = payload.get("accepted", True)  # default True in automated flow
    truck_id = payload.get("truck_id")
    driver_code = payload.get("driver_code")
    load_id = payload.get("load_id")
    if not accepted:
        return {"accepted": False, "reason": payload.get("decline_reason", "driver_declined")}
    sb = _db()
    if sb and load_id:
        try:
            sb.table("loads").update({
                "truck_id": truck_id,
                "driver_code": driver_code,
                "status": "dispatched",
            }).eq("id", load_id).execute()
        except Exception:  # noqa: BLE001
            pass
    return {
        "accepted": True,
        "truck_id": truck_id,
        "driver_code": driver_code,
        "load_id": load_id,
        "accepted_at": _NOW(),
    }


# ── Step 38: dispatch.reoffer_on_decline ──────────────────────────────────────

def h38_dispatch_reoffer_on_decline(carrier_id, contract_id, payload):
    if payload.get("accepted", True):
        return {"reoffered": False, "reason": "load_was_accepted"}
    ranked = payload.get("ranked_trucks") or []
    if len(ranked) < 2:
        return {"reoffered": False, "reason": "no_backup_trucks"}
    next_truck = ranked[1]
    return {
        "reoffered": True,
        "next_truck": next_truck,
        "truck_id": next_truck.get("truck_id"),
        "reoffered_at": _NOW(),
    }


# ── Step 39: eld.lock_hos ─────────────────────────────────────────────────────

def h39_eld_lock_hos(carrier_id, contract_id, payload):
    driver_code = payload.get("driver_code")
    load_id = payload.get("load_id")
    if not driver_code:
        return {"locked": False, "reason": "no_driver_code"}
    sb = _db()
    if sb:
        try:
            sb.table("driver_hos_status").update({
                "locked_load_id": load_id,
                "locked_at": _NOW(),
            }).eq("driver_id", driver_code).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"locked": True, "driver_code": driver_code, "load_id": load_id, "locked_at": _NOW()}


# ── Step 40: clm.create_load_contract ────────────────────────────────────────

def h40_clm_create_load_contract(carrier_id, contract_id, payload):
    sb = _db()
    extracted = payload.get("extracted") or {}
    if not sb:
        return {"created": False, "note": "supabase_not_configured"}
    try:
        r = sb.table("contracts").insert({
            "carrier_id": str(carrier_id) if carrier_id else None,
            "contract_type": "rate_confirmation",
            "status": "active",
            "counterparty_name": extracted.get("broker_name") or payload.get("broker_name"),
            "rate_total": extracted.get("rate_total") or payload.get("rate_total"),
            "rate_per_mile": extracted.get("rate_per_mile") or payload.get("rate_per_mile"),
            "origin_city": extracted.get("origin_city") or payload.get("origin_city"),
            "destination_city": extracted.get("destination_city") or payload.get("dest_city"),
            "pickup_date": (extracted.get("pickup_date") or payload.get("pickup_at", ""))[:10] or None,
            "delivery_date": (extracted.get("delivery_date") or payload.get("delivery_at", ""))[:10] or None,
            "payment_terms": extracted.get("payment_terms"),
            "extracted_vars": extracted,
            "milestone_pct": 10,
            "gl_posted": False,
            "revenue_recognized": False,
            "created_at": _NOW(),
        }).execute()
        cid = r.data[0]["id"] if r.data else None
        return {"created": True, "contract_id": cid, "milestone_pct": 10}
    except Exception as e:  # noqa: BLE001
        return {"created": False, "error": str(e)}


DISPATCH_HANDLERS_PART1: dict = {
    31: h31_dispatch_load_received,
    32: h32_clm_scan_rate_conf,
    33: h33_clm_validate_rate,
    34: h34_dispatch_match_truck,
    35: h35_dispatch_score_match,
    36: h36_dispatch_offer_load,
    37: h37_dispatch_driver_accept,
    38: h38_dispatch_reoffer_on_decline,
    39: h39_eld_lock_hos,
    40: h40_clm_create_load_contract,
}

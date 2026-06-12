"""Light Fleet — Trip Dispatch handlers (steps 221–240).

Triggered when a new light_vehicle_trip is created (status=pending).
Handles driver matching, rate calculation, assignment, and notifications.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
import logging

log = logging.getLogger("3ll.execution.lf_dispatch")

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731

_TRIP_TYPE_LABELS: dict[str, str] = {
    "nemt": "NEMT — Medical Transport",
    "executive": "Executive — Corporate Ride",
    "courier": "Courier — Package Delivery",
    "gig": "Gig — On-Demand Ride",
}

_RATE_PER_MILE: dict[str, float] = {
    "nemt": 3.50,
    "executive": 4.50,
    "courier": 2.75,
    "gig": 2.50,
}


def _db():
    try:
        from ...supabase_client import get_supabase
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _trip(trip_id) -> dict:
    if not trip_id:
        return {}
    sb = _db()
    if not sb:
        return {}
    try:
        r = (
            sb.table("light_vehicle_trips")
            .select("*")
            .eq("id", str(trip_id))
            .maybe_single()
            .execute()
        )
        return r.data or {}
    except Exception:  # noqa: BLE001
        return {}


# ── Step 221: trip.receive ────────────────────────────────────────────────────

def h221_trip_receive(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        t = _trip(trip_id)
        return {
            "received": True,
            "trip_id": trip_id,
            "trip_type": t.get("trip_type") or payload.get("trip_type"),
            "pickup_address": t.get("pickup_address") or payload.get("pickup_address"),
            "dropoff_address": t.get("dropoff_address") or payload.get("dropoff_address"),
            "passenger_name": t.get("passenger_name") or payload.get("passenger_name"),
            "scheduled_at": t.get("scheduled_at") or payload.get("scheduled_at"),
            "status": t.get("status") or payload.get("status", "pending"),
        }
    except Exception as e:  # noqa: BLE001
        return {"received": False, "error": str(e)}


# ── Step 222: validate.addresses ─────────────────────────────────────────────

def h222_validate_addresses(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        t = _trip(trip_id)
        pickup = t.get("pickup_address") or payload.get("pickup_address") or ""
        dropoff = t.get("dropoff_address") or payload.get("dropoff_address") or ""
        pickup_ok = bool(pickup and pickup.strip())
        dropoff_ok = bool(dropoff and dropoff.strip())
        return {
            "validated": pickup_ok and dropoff_ok,
            "pickup_ok": pickup_ok,
            "dropoff_ok": dropoff_ok,
            "pickup_address": pickup,
            "dropoff_address": dropoff,
        }
    except Exception as e:  # noqa: BLE001
        return {"validated": False, "error": str(e)}


# ── Step 223: classify.type ───────────────────────────────────────────────────

def h223_classify_type(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        t = _trip(trip_id)
        trip_type = t.get("trip_type") or payload.get("trip_type", "gig")
        valid_types = list(_TRIP_TYPE_LABELS.keys())
        type_label = _TRIP_TYPE_LABELS.get(trip_type, f"Unknown — {trip_type}")
        return {
            "trip_type": trip_type,
            "type_label": type_label,
            "valid": trip_type in valid_types,
        }
    except Exception as e:  # noqa: BLE001
        return {"trip_type": None, "error": str(e)}


# ── Step 224: estimate.distance ──────────────────────────────────────────────

def h224_estimate_distance(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        t = _trip(trip_id)
        estimated_miles = (
            t.get("estimated_miles")
            or payload.get("estimated_miles")
            or 15.0
        )
        estimated_miles = float(estimated_miles)
        estimated_minutes = round(estimated_miles * 2.5)
        return {
            "estimated_miles": estimated_miles,
            "estimated_minutes": estimated_minutes,
        }
    except Exception as e:  # noqa: BLE001
        return {"estimated_miles": 15.0, "estimated_minutes": 38, "error": str(e)}


# ── Step 225: calculate.rate ──────────────────────────────────────────────────

def h225_calculate_rate(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        t = _trip(trip_id)
        rate_total = t.get("rate_total") or payload.get("rate_total")
        trip_type = t.get("trip_type") or payload.get("trip_type", "gig")
        estimated_miles = float(
            payload.get("estimated_miles") or t.get("estimated_miles") or 15.0
        )
        if rate_total:
            return {
                "rate_total": float(rate_total),
                "rate_per_mile": t.get("rate_per_mile"),
                "calculation_method": "existing",
            }
        rate_per_mile = _RATE_PER_MILE.get(trip_type, 2.50)
        rate_total = round(rate_per_mile * estimated_miles, 2)
        sb = _db()
        if sb and trip_id:
            try:
                sb.table("light_vehicle_trips").update({
                    "rate_total": rate_total,
                    "rate_per_mile": rate_per_mile,
                }).eq("id", str(trip_id)).execute()
            except Exception:  # noqa: BLE001
                pass
        return {
            "rate_total": rate_total,
            "rate_per_mile": rate_per_mile,
            "calculation_method": "calculated",
            "estimated_miles": estimated_miles,
            "trip_type": trip_type,
        }
    except Exception as e:  # noqa: BLE001
        return {"rate_total": None, "error": str(e)}


# ── Step 226: check.nemt_auth ─────────────────────────────────────────────────

def h226_check_nemt_auth(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        t = _trip(trip_id)
        trip_type = t.get("trip_type") or payload.get("trip_type", "gig")
        if trip_type != "nemt":
            return {"skipped": True, "reason": "not_a_nemt_trip", "trip_type": trip_type}
        auth_number = t.get("insurance_auth_number") or payload.get("insurance_auth_number")
        insurance_provider = t.get("insurance_provider") or payload.get("insurance_provider")
        return {
            "auth_present": bool(auth_number),
            "auth_number": auth_number,
            "insurance_provider": insurance_provider,
        }
    except Exception as e:  # noqa: BLE001
        return {"auth_present": False, "error": str(e)}


# ── Step 227: match.driver ────────────────────────────────────────────────────

def h227_match_driver(carrier_id, contract_id, payload) -> dict:
    try:
        trip_type    = payload.get("trip_type", "gig")
        pickup_addr  = payload.get("pickup_address") or payload.get("origin_address") or ""
        sb = _db()
        candidates: list[dict] = []
        disqualified: list[dict] = []

        if sb:
            try:
                from datetime import date
                from ..handlers.lf_onboarding import _SERVICE_RULES, _vehicle_age  # noqa: PLC0415
                current_year = date.today().year
                rules = _SERVICE_RULES.get(trip_type, _SERVICE_RULES["gig"])
                max_age      = rules["max_age"]
                allowed_types = rules["types"]  # None = any type

                rows = (
                    sb.table("light_vehicle_drivers")
                    .select(
                        "id,name,vehicle_type,vehicle_year,total_trips,approved_services,"
                        "mvr_status,background_check_status,last_lat,last_lng"
                    )
                    .eq("status", "active")
                    .execute()
                    .data or []
                )
                for row in rows:
                    services      = row.get("approved_services") or []
                    vehicle_type  = (row.get("vehicle_type") or "sedan").lower()
                    vehicle_year  = row.get("vehicle_year")
                    age           = _vehicle_age(vehicle_year)
                    mvr_ok        = row.get("mvr_status") not in ("flagged", "suspended", "failed")
                    bg_ok         = row.get("background_check_status") not in ("flagged", "failed")

                    # ── Hard gates ────────────────────────────────────────────
                    if trip_type not in services:
                        disqualified.append({"id": row["id"], "reason": f"not in approved_services for {trip_type}"})
                        continue
                    if not mvr_ok:
                        disqualified.append({"id": row["id"], "reason": f"mvr_status={row.get('mvr_status')}"})
                        continue
                    if not bg_ok:
                        disqualified.append({"id": row["id"], "reason": f"bg_status={row.get('background_check_status')}"})
                        continue
                    if allowed_types and vehicle_type not in allowed_types:
                        disqualified.append({"id": row["id"], "reason": f"vehicle_type '{vehicle_type}' not allowed for {trip_type}"})
                        continue
                    if age is not None and age > max_age:
                        disqualified.append({"id": row["id"], "reason": f"vehicle age {age}yr exceeds {max_age}yr limit for {trip_type}"})
                        continue

                    candidates.append({
                        "id":           row["id"],
                        "name":         row.get("name"),
                        "vehicle_type": vehicle_type,
                        "vehicle_year": vehicle_year,
                        "total_trips":  row.get("total_trips", 0),
                        "last_lat":     row.get("last_lat"),
                        "last_lng":     row.get("last_lng"),
                    })
            except Exception:  # noqa: BLE001
                pass

        # Prefer most experienced driver (most trips completed)
        candidates.sort(key=lambda d: d.get("total_trips", 0), reverse=True)
        best_match_id = candidates[0]["id"] if candidates else None

        return {
            "candidates":       candidates,
            "candidates_found": len(candidates),
            "best_match_id":    best_match_id,
            "disqualified":     disqualified,
            "trip_type":        trip_type,
        }
    except Exception as e:  # noqa: BLE001
        return {"candidates": [], "candidates_found": 0, "best_match_id": None, "error": str(e)}


# ── Step 228: offer.driver ────────────────────────────────────────────────────

def h228_offer_driver(carrier_id, contract_id, payload) -> dict:
    try:
        best_match_id = payload.get("best_match_id")
        trip_id = payload.get("trip_id")
        if not best_match_id:
            return {
                "offer_sent": False,
                "reason": "no_available_drivers",
            }
        sb = _db()
        driver_name = None
        if sb and best_match_id:
            try:
                r = (
                    sb.table("light_vehicle_drivers")
                    .select("name")
                    .eq("id", str(best_match_id))
                    .maybe_single()
                    .execute()
                )
                driver_name = (r.data or {}).get("name")
            except Exception:  # noqa: BLE001
                pass
        offered_at = _NOW()
        log.info("Driver offer push simulated → driver %s, trip %s", best_match_id, trip_id)
        return {
            "offer_sent": True,
            "driver_id": str(best_match_id),
            "driver_name": driver_name,
            "trip_id": trip_id,
            "offered_at": offered_at,
        }
    except Exception as e:  # noqa: BLE001
        return {"offer_sent": False, "error": str(e)}


# ── Step 229: confirm.acceptance ─────────────────────────────────────────────

def h229_confirm_acceptance(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        best_match_id = payload.get("best_match_id") or payload.get("driver_id")
        assigned_at = _NOW()
        sb = _db()
        if sb and trip_id and best_match_id:
            try:
                sb.table("light_vehicle_trips").update({
                    "driver_id": str(best_match_id),
                    "status": "assigned",
                    "assigned_at": assigned_at,
                }).eq("id", str(trip_id)).execute()
            except Exception:  # noqa: BLE001
                pass
        return {
            "accepted": True,
            "driver_id": str(best_match_id) if best_match_id else None,
            "trip_id": trip_id,
            "assigned_at": assigned_at,
        }
    except Exception as e:  # noqa: BLE001
        return {"accepted": False, "error": str(e)}


# ── Step 230: lock.assignment ─────────────────────────────────────────────────

def h230_lock_assignment(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        t = _trip(trip_id)
        driver_id = t.get("driver_id") or payload.get("driver_id") or payload.get("best_match_id")
        status = t.get("status") or payload.get("status")
        locked = bool(driver_id and status == "assigned")
        return {
            "locked": locked,
            "driver_id": str(driver_id) if driver_id else None,
            "trip_id": trip_id,
            "status": status,
        }
    except Exception as e:  # noqa: BLE001
        return {"locked": False, "error": str(e)}


# ── Step 231: notify.passenger ───────────────────────────────────────────────

def h231_notify_passenger(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        t = _trip(trip_id)
        passenger_phone = (
            t.get("passenger_phone") or payload.get("passenger_phone") or "unknown"
        )
        scheduled_at = t.get("scheduled_at") or payload.get("scheduled_at", "TBD")
        message = (
            f"Your driver is on the way! "
            f"Expected arrival: {scheduled_at}. "
            f"Trip ID: {trip_id}."
        )
        log.info("Passenger SMS simulated to %s: %s", passenger_phone, message)
        return {
            "notification_sent": True,
            "phone": passenger_phone,
            "message": message,
        }
    except Exception as e:  # noqa: BLE001
        return {"notification_sent": False, "error": str(e)}


# ── Step 232: start.gps_tracking ─────────────────────────────────────────────

def h232_start_gps_tracking(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        driver_id = payload.get("driver_id") or payload.get("best_match_id") or carrier_id
        tracking_session = f"lf-{str(trip_id)[:8]}" if trip_id else "lf-unknown"
        log.info("GPS tracking session started: %s", tracking_session)
        return {
            "tracking_started": True,
            "driver_id": str(driver_id) if driver_id else None,
            "trip_id": trip_id,
            "tracking_session": tracking_session,
        }
    except Exception as e:  # noqa: BLE001
        return {"tracking_started": False, "error": str(e)}


# ── Step 233: create.doc_expectation ─────────────────────────────────────────

def h233_create_doc_expectation(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        trip_type = payload.get("trip_type", "gig")
        nemt_log_required = trip_type == "nemt"
        return {
            "pod_required": True,
            "trip_id": trip_id,
            "doc_types": ["proof_of_delivery"],
            "nemt_log_required": nemt_log_required,
        }
    except Exception as e:  # noqa: BLE001
        return {"pod_required": False, "error": str(e)}


# ── Step 234: notify.corporate ───────────────────────────────────────────────

def h234_notify_corporate(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        trip_type = payload.get("trip_type", "gig")
        executive_account_id = payload.get("executive_account_id")
        if trip_type != "executive" or not executive_account_id:
            return {"skipped": True, "reason": "not_executive_trip_or_no_account_id"}
        sb = _db()
        contact_email = None
        if sb:
            try:
                r = (
                    sb.table("executive_accounts")
                    .select("contact_email")
                    .eq("id", str(executive_account_id))
                    .maybe_single()
                    .execute()
                )
                contact_email = (r.data or {}).get("contact_email")
            except Exception:  # noqa: BLE001
                pass
        log.info(
            "Corporate notification simulated → %s for trip %s",
            contact_email, trip_id
        )
        return {
            "corporate_notified": True,
            "contact_email": contact_email,
            "executive_account_id": str(executive_account_id),
        }
    except Exception as e:  # noqa: BLE001
        return {"corporate_notified": False, "error": str(e)}


# ── Step 235: log.auth_code ───────────────────────────────────────────────────

def h235_log_auth_code(carrier_id, contract_id, payload) -> dict:
    try:
        trip_type = payload.get("trip_type", "gig")
        if trip_type != "nemt":
            return {"skipped": True, "reason": "not_a_nemt_trip"}
        auth_number = payload.get("insurance_auth_number") or payload.get("auth_number")
        trip_id = payload.get("trip_id")
        sb = _db()
        if sb and trip_id and auth_number:
            try:
                sb.table("light_vehicle_trips").update({
                    "insurance_auth_number": auth_number,
                    "auth_logged_at": _NOW(),
                }).eq("id", str(trip_id)).execute()
            except Exception:  # noqa: BLE001
                pass
        return {
            "auth_logged": True,
            "auth_number": auth_number,
            "trip_id": trip_id,
        }
    except Exception as e:  # noqa: BLE001
        return {"auth_logged": False, "error": str(e)}


# ── Step 236: dispatch.email ──────────────────────────────────────────────────

def h236_dispatch_email(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id") or ""
        trip_type = payload.get("trip_type", "gig")
        subject = f"Trip {str(trip_id)[:8]} dispatched — {trip_type.upper()}"
        log.info("Dispatch email simulated: %s", subject)
        return {
            "email_sent": True,
            "to": "dispatch@3lakeslogistics.com",
            "subject": subject,
        }
    except Exception as e:  # noqa: BLE001
        return {"email_sent": False, "error": str(e)}


# ── Step 237: ledger.preview ──────────────────────────────────────────────────

def h237_ledger_preview(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        trip_type = payload.get("trip_type", "gig")
        pickup_address = payload.get("pickup_address")
        dropoff_address = payload.get("dropoff_address")
        rate_total = payload.get("rate_total")
        sb = _db()
        if not sb:
            return {"ledger_written": False, "note": "supabase_not_configured"}
        from ...atomic_ledger.service import write_event
        from ...atomic_ledger.models import AtomicEvent
        row = write_event(AtomicEvent(
            event_type="lf_trip_dispatched",
            event_source="execution_engine.lf_dispatch",
            logistics_payload={
                "trip_id": trip_id,
                "trip_type": trip_type,
                "pickup_address": pickup_address,
                "dropoff_address": dropoff_address,
            },
            financial_payload={
                "estimated_revenue": rate_total,
            },
        ))
        ledger_id = row.get("id")
        return {
            "ledger_written": True,
            "ledger_id": ledger_id,
        }
    except Exception as e:  # noqa: BLE001
        return {"ledger_written": False, "error": str(e)}


# ── Step 238: eta.broadcast ───────────────────────────────────────────────────

def h238_eta_broadcast(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        t = _trip(trip_id)
        estimated_arrival = (
            t.get("scheduled_at") or payload.get("scheduled_at") or "TBD"
        )
        return {
            "eta_broadcast": True,
            "estimated_arrival": estimated_arrival,
            "driver_notified": True,
            "passenger_notified": True,
        }
    except Exception as e:  # noqa: BLE001
        return {"eta_broadcast": False, "error": str(e)}


# ── Step 239: dispatch.complete ───────────────────────────────────────────────

def h239_dispatch_complete(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        driver_id = payload.get("driver_id") or payload.get("best_match_id")
        rate_total = payload.get("rate_total")
        sb = _db()
        if sb and trip_id:
            try:
                sb.table("light_vehicle_trips").update({
                    "dispatcher_notes": "Dispatch workflow complete.",
                }).eq("id", str(trip_id)).execute()
            except Exception:  # noqa: BLE001
                pass
        return {
            "dispatch_complete": True,
            "trip_id": trip_id,
            "driver_id": str(driver_id) if driver_id else None,
            "rate_total": rate_total,
        }
    except Exception as e:  # noqa: BLE001
        return {"dispatch_complete": False, "error": str(e)}


# ── Step 240: eagle_eye.update ────────────────────────────────────────────────

def h240_eagle_eye_update(carrier_id, contract_id, payload) -> dict:
    try:
        trip_id = payload.get("trip_id")
        return {
            "eagle_eye_refreshed": True,
            "trip_id": trip_id,
            "status": "assigned",
            "board_updated_at": _NOW(),
        }
    except Exception as e:  # noqa: BLE001
        return {"eagle_eye_refreshed": False, "error": str(e)}


# ── Dispatch table ────────────────────────────────────────────────────────────

LF_DISPATCH_HANDLERS: dict[int, callable] = {
    221: h221_trip_receive,
    222: h222_validate_addresses,
    223: h223_classify_type,
    224: h224_estimate_distance,
    225: h225_calculate_rate,
    226: h226_check_nemt_auth,
    227: h227_match_driver,
    228: h228_offer_driver,
    229: h229_confirm_acceptance,
    230: h230_lock_assignment,
    231: h231_notify_passenger,
    232: h232_start_gps_tracking,
    233: h233_create_doc_expectation,
    234: h234_notify_corporate,
    235: h235_log_auth_code,
    236: h236_dispatch_email,
    237: h237_ledger_preview,
    238: h238_eta_broadcast,
    239: h239_dispatch_complete,
    240: h240_eagle_eye_update,
}

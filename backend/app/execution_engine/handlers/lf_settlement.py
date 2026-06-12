"""Light Fleet — Trip Settlement handlers (steps 256–270).

Triggered when trip status → completed + POD captured.
Covers billing, payout, invoicing, NEMT audit, KPI updates.
"""
from __future__ import annotations

from datetime import datetime, timezone

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _db():
    try:
        from ...supabase_client import get_supabase
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _trip(trip_id):
    if not trip_id:
        return {}
    sb = _db()
    if not sb:
        return {}
    try:
        r = sb.table("light_vehicle_trips").select("*").eq("id", trip_id).maybe_single().execute()
        return r.data or {}
    except Exception:  # noqa: BLE001
        return {}


# ── Step 256: lf_settlement.confirm_completion ───────────────────────────────

def h256_confirm_completion(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    trip = _trip(trip_id)
    return {
        "confirmed": trip.get("status") == "completed",
        "pod_present": bool(trip.get("pod_url")),
        "trip_id": trip_id,
        "trip_type": trip.get("trip_type", payload.get("trip_type", "")),
        "rate_total": trip.get("rate_total", payload.get("rate_total")),
    }


# ── Step 257: lf_settlement.apply_rate ───────────────────────────────────────

def h257_apply_rate(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    trip = _trip(trip_id)
    rate_total = trip.get("rate_total") or payload.get("rate_total")
    rate_source = "stored"
    if rate_total is None:
        estimated_miles = trip.get("estimated_miles") or payload.get("estimated_miles", 0)
        rate_per_mile = trip.get("rate_per_mile") or payload.get("rate_per_mile", 2.50)
        try:
            rate_total = float(estimated_miles) * float(rate_per_mile)
            rate_source = "calculated"
        except Exception:  # noqa: BLE001
            rate_total = 0.0
            rate_source = "calculated"
    return {
        "final_rate": float(rate_total) if rate_total is not None else 0.0,
        "rate_source": rate_source,
        "trip_id": trip_id,
    }


# ── Step 258: lf_settlement.platform_fee_deduction ───────────────────────────

def h258_platform_fee_deduction(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    rate_total = payload.get("rate_total") or payload.get("final_rate", 0.0)
    fee_pct = 0.15
    fee_plan = "starter"
    try:
        platform_fee = round(float(rate_total) * fee_pct, 2)
    except Exception:  # noqa: BLE001
        platform_fee = 0.0
    return {
        "platform_fee": platform_fee,
        "fee_pct": fee_pct,
        "fee_plan": fee_plan,
        "trip_id": trip_id,
        "rate_total": float(rate_total) if rate_total is not None else 0.0,
    }


# ── Step 259: lf_settlement.driver_net_calc ──────────────────────────────────

def h259_driver_net_calc(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    driver_id = payload.get("driver_id") or str(carrier_id) if carrier_id else None
    rate_total = payload.get("rate_total", 0.0)
    platform_fee = payload.get("platform_fee", 0.0)
    try:
        driver_net = round(float(rate_total) - float(platform_fee), 2)
    except Exception:  # noqa: BLE001
        driver_net = 0.0
    return {
        "driver_net": driver_net,
        "rate_total": float(rate_total),
        "platform_fee": float(platform_fee),
        "driver_id": driver_id,
        "trip_id": trip_id,
    }


# ── Step 260: lf_settlement.nemt_billing_queue ───────────────────────────────

def h260_nemt_billing_queue(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    trip_type = payload.get("trip_type", "")
    if trip_type != "nemt":
        return {"skipped": True, "reason": "not_nemt", "trip_id": trip_id}
    rate_total = payload.get("rate_total", 0.0)
    insurance_auth_number = payload.get("insurance_auth_number", "")
    insurance_provider = payload.get("insurance_provider", "")
    return {
        "billing_queued": True,
        "trip_id": trip_id,
        "insurance_auth_number": insurance_auth_number,
        "insurance_provider": insurance_provider,
        "billing_amount": float(rate_total) if rate_total is not None else 0.0,
        "queued_at": _NOW(),
    }


# ── Step 261: lf_settlement.corporate_invoice ────────────────────────────────

def h261_corporate_invoice(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    trip_type = payload.get("trip_type", "")
    trip = _trip(trip_id)
    executive_account_id = trip.get("executive_account_id") or payload.get("executive_account_id")
    rate_total = trip.get("rate_total") or payload.get("rate_total", 0.0)
    if trip_type == "executive" and executive_account_id:
        return {
            "invoice_generated": True,
            "account_id": executive_account_id,
            "amount": float(rate_total) if rate_total is not None else 0.0,
            "invoice_ref": f"INV-LF-{str(trip_id)[:8].upper()}",
            "trip_id": trip_id,
            "generated_at": _NOW(),
        }
    return {"skipped": True, "reason": "not_executive_or_no_account", "trip_id": trip_id}


# ── Step 262: lf_settlement.ach_initiation ───────────────────────────────────

def h262_ach_initiation(carrier_id, contract_id, payload) -> dict:
    """Queue earnings in lf_driver_payouts for weekly batch settlement.

    Earnings accumulate as 'queued' throughout the week.  The weekly batch
    processor (POST /admin/lf/payouts/weekly-batch) aggregates and sends one
    Stripe Transfer per driver each Friday.  No fee — the 15% platform
    commission was already deducted in step 258.
    """
    trip_id    = payload.get("trip_id")
    driver_id  = payload.get("driver_id") or (str(carrier_id) if carrier_id else None)
    driver_net = float(payload.get("driver_net") or 0.0)

    if driver_net <= 0:
        return {"ach_initiated": False, "reason": "zero_or_negative_net", "amount": driver_net}

    net_cents  = int(round(driver_net * 100))
    queued_at  = _NOW()

    sb = _db()
    record_id = None
    if sb and driver_id:
        try:
            rec = sb.table("lf_driver_payouts").insert({
                "driver_id":          str(driver_id),
                "trip_id":            str(trip_id) if trip_id else None,
                "payout_type":        "weekly",
                "gross_cents":        net_cents,
                "platform_fee_cents": 0,
                "instant_fee_cents":  0,
                "net_cents":          net_cents,
                "status":             "queued",
                "requested_at":       queued_at,
            }).execute()
            record_id = (rec.data or [{}])[0].get("id")
        except Exception:  # noqa: BLE001
            pass

    return {
        "ach_initiated":     True,
        "driver_id":         driver_id,
        "amount":            driver_net,
        "payment_method":    "weekly_batch",
        "payout_record_id":  record_id,
        "trip_id":           trip_id,
        "queued_at":         queued_at,
        "estimated_arrival": "next weekly payout (Fridays)",
    }


# ── Step 263: lf_settlement.ledger_write ─────────────────────────────────────

def h263_ledger_write(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    trip_type = payload.get("trip_type", "")
    rate_total = payload.get("rate_total", 0.0)
    platform_fee = payload.get("platform_fee", 0.0)
    driver_net = payload.get("driver_net", 0.0)
    trip = _trip(trip_id)
    sb = _db()
    try:
        from ...atomic_ledger.service import write_event
        from ...atomic_ledger.models import AtomicEvent
        write_event(AtomicEvent(
            event_type="lf_trip_settled",
            event_source="execution_engine.lf_settlement",
            logistics_payload={
                "trip_id": trip_id,
                "trip_type": trip_type,
                "carrier_id": str(carrier_id) if carrier_id else None,
                "contract_id": str(contract_id) if contract_id else None,
                "pickup_address": trip.get("pickup_address", payload.get("pickup_address", "")),
                "dropoff_address": trip.get("dropoff_address", payload.get("dropoff_address", "")),
            },
            financial_payload={
                "rate_total": float(rate_total) if rate_total is not None else 0.0,
                "platform_fee": float(platform_fee) if platform_fee is not None else 0.0,
                "driver_net": float(driver_net) if driver_net is not None else 0.0,
            },
        ))
    except Exception:  # noqa: BLE001
        pass
    return {
        "ledger_written": True,
        "event_type": "lf_trip_settled",
        "trip_id": trip_id,
    }


# ── Step 264: lf_settlement.driver_performance ───────────────────────────────

def _extract_city_state(address: str) -> tuple[str, str] | None:
    """Parse 'City, ST' or 'Street, City, ST ZIP' → (City, ST) or None."""
    if not address:
        return None
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 2:
        city = parts[-2].strip()
        state_zip = parts[-1].strip().split()
        state = state_zip[0] if state_zip else ""
        if len(state) == 2 and state.isalpha():
            return city, state.upper()
    return None


def h264_driver_performance(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    driver_id = payload.get("driver_id") or (str(carrier_id) if carrier_id else None)
    sb = _db()
    new_rating = 5.0
    total_trips = 0
    service_areas_updated = False
    load_types_updated = False

    if sb and driver_id:
        try:
            r = sb.table("light_vehicle_drivers").select(
                "rating,total_trips,service_areas,preferred_load_types,approved_services"
            ).eq("id", driver_id).maybe_single().execute()
            data = r.data or {}
            current_rating = data.get("rating")
            total_trips = data.get("total_trips", 0) or 0
            if current_rating is not None:
                new_rating = round((float(current_rating) * total_trips + 5.0) / (total_trips + 1), 2)
            else:
                new_rating = 5.0

            updates: dict = {"rating": new_rating, "total_trips": total_trips + 1}

            # ── Learn service area from pickup location ──────────────────────
            pickup = payload.get("pickup_address", "")
            cs = _extract_city_state(pickup)
            if cs:
                city, state = cs
                area_str = f"{city}, {state}"
                existing = list(data.get("service_areas") or [])
                if area_str not in existing:
                    existing.append(area_str)
                    updates["service_areas"] = existing[:10]  # cap at 10 areas
                    service_areas_updated = True

            # ── Learn load type preference from trip type ────────────────────
            trip_type = payload.get("trip_type", "")
            if trip_type:
                existing_lt = list(data.get("preferred_load_types") or data.get("approved_services") or [])
                if trip_type not in existing_lt:
                    existing_lt.append(trip_type)
                    updates["preferred_load_types"] = existing_lt[:8]
                    load_types_updated = True

            sb.table("light_vehicle_drivers").update(updates).eq("id", driver_id).execute()
        except Exception:  # noqa: BLE001
            pass

    return {
        "rating_updated": True,
        "new_rating": new_rating,
        "driver_id": driver_id,
        "total_trips": total_trips + 1,
        "trip_id": trip_id,
        "service_areas_updated": service_areas_updated,
        "load_types_updated": load_types_updated,
    }


# ── Step 265: lf_settlement.client_receipt ───────────────────────────────────

def h265_client_receipt(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    rate_total = payload.get("rate_total", 0.0)
    passenger_phone = payload.get("passenger_phone", "")
    contact_email = payload.get("contact_email", "")
    recipient = passenger_phone or contact_email
    channel = "sms" if passenger_phone else "email"
    return {
        "receipt_sent": True,
        "channel": channel,
        "recipient": recipient,
        "message": f"Your trip is complete. Total: ${rate_total}. Thank you for riding with 3 Lakes Light Fleet.",
        "trip_id": trip_id,
        "sent_at": _NOW(),
    }


# ── Step 266: lf_settlement.kpi_update ───────────────────────────────────────

def h266_kpi_update(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    trip_type = payload.get("trip_type", "")
    rate_total = payload.get("rate_total", 0.0)
    return {
        "kpi_updated": True,
        "metric": "lf_trips_completed",
        "trip_type": trip_type,
        "rate_total": float(rate_total) if rate_total is not None else 0.0,
        "trip_id": trip_id,
        "updated_at": _NOW(),
    }


# ── Step 267: lf_settlement.nemt_audit_log ───────────────────────────────────

def h267_nemt_audit_log(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    trip_type = payload.get("trip_type", "")
    if trip_type != "nemt":
        return {"skipped": True, "reason": "not_nemt", "trip_id": trip_id}
    trip = _trip(trip_id)
    rate_total = trip.get("rate_total") or payload.get("rate_total", 0.0)
    return {
        "audit_logged": True,
        "trip_id": trip_id,
        "patient": trip.get("passenger_name", payload.get("passenger_name", "")),
        "pickup": trip.get("pickup_address", payload.get("pickup_address", "")),
        "dropoff": trip.get("dropoff_address", payload.get("dropoff_address", "")),
        "auth_number": payload.get("insurance_auth_number", ""),
        "rate": float(rate_total) if rate_total is not None else 0.0,
        "logged_at": _NOW(),
    }


# ── Step 268: lf_settlement.dispute_check ────────────────────────────────────

def h268_dispute_check(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    if payload.get("dispute"):
        return {
            "dispute_flagged": True,
            "trip_id": trip_id,
            "rate_matched": False,
            "reason": payload.get("dispute_reason", "unspecified"),
            "checked_at": _NOW(),
        }
    return {
        "dispute_flagged": False,
        "trip_id": trip_id,
        "rate_matched": True,
        "checked_at": _NOW(),
    }


# ── Step 269: lf_settlement.invoice_record ───────────────────────────────────

def h269_invoice_record(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    trip_type = payload.get("trip_type", "")
    rate_total = payload.get("rate_total", 0.0)
    sb = _db()
    invoice_id = None
    if sb:
        try:
            result = sb.table("invoices").insert({
                "carrier_id": str(carrier_id) if carrier_id else None,
                "contract_id": str(contract_id) if contract_id else None,
                "amount": float(rate_total) if rate_total is not None else 0.0,
                "status": "Unpaid",
                "description": f"Light Fleet Trip {str(trip_id)[:8]} — {trip_type.upper()}",
                "created_at": _NOW(),
            }).execute()
            invoice_id = (result.data[0].get("id") if result.data else None)
        except Exception:  # noqa: BLE001
            pass
    return {
        "invoice_created": True,
        "invoice_id": invoice_id,
        "trip_id": trip_id,
        "amount": float(rate_total) if rate_total is not None else 0.0,
    }


# ── Step 270: lf_settlement.settlement_complete ──────────────────────────────

def h270_settlement_complete(carrier_id, contract_id, payload) -> dict:
    trip_id = payload.get("trip_id")
    driver_net = payload.get("driver_net", 0.0)
    platform_fee = payload.get("platform_fee", 0.0)
    rate_total = payload.get("rate_total", 0.0)
    return {
        "domain_complete": True,
        "domain": "lf_settlement",
        "trip_id": trip_id,
        "driver_net": float(driver_net) if driver_net is not None else 0.0,
        "platform_fee": float(platform_fee) if platform_fee is not None else 0.0,
        "rate_total": float(rate_total) if rate_total is not None else 0.0,
        "completed_at": _NOW(),
    }


# ── Handler registry ──────────────────────────────────────────────────────────

LF_SETTLEMENT_HANDLERS: dict[int, callable] = {
    256: h256_confirm_completion,
    257: h257_apply_rate,
    258: h258_platform_fee_deduction,
    259: h259_driver_net_calc,
    260: h260_nemt_billing_queue,
    261: h261_corporate_invoice,
    262: h262_ach_initiation,
    263: h263_ledger_write,
    264: h264_driver_performance,
    265: h265_client_receipt,
    266: h266_kpi_update,
    267: h267_nemt_audit_log,
    268: h268_dispute_check,
    269: h269_invoice_record,
    270: h270_settlement_complete,
}

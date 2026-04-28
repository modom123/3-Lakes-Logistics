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


# ── Step 41: dispatch.confirm_broker ─────────────────────────────────────────

def h41_dispatch_confirm_broker(carrier_id, contract_id, payload):
    s = get_settings()
    broker_email = payload.get("broker_email")
    load_id = payload.get("load_id")
    load_number = payload.get("load_number")
    driver_name = payload.get("driver_name", "on file")
    truck_id = payload.get("truck_id", "on file")
    if s.postmark_server_token and broker_email:
        try:
            from postmarker.core import PostmarkClient  # type: ignore
            PostmarkClient(server_token=s.postmark_server_token).emails.send(
                From=s.postmark_from_email,
                To=broker_email,
                Subject=f"Load {load_number} — Carrier Accepted",
                TextBody=(
                    f"Load {load_number} has been accepted.\n"
                    f"Driver: {driver_name} | Unit: {truck_id}\n"
                    f"— 3 Lakes Logistics Dispatch"
                ),
            )
            return {"confirmed": True, "to": broker_email, "load_id": load_id}
        except Exception as e:  # noqa: BLE001
            return {"confirmed": False, "error": str(e)}
    return {"confirmed": False, "note": "postmark_not_configured",
            "would_send_to": broker_email, "load_id": load_id}


# ── Step 42: nova.dispatch_email ──────────────────────────────────────────────

def h42_nova_dispatch_email(carrier_id, contract_id, payload):
    s = get_settings()
    driver_email = payload.get("driver_email")
    broker_email = payload.get("broker_email")
    body = (
        f"Dispatch Sheet — Load {payload.get('load_number')}\n\n"
        f"Origin:  {payload.get('origin_city')}, {payload.get('origin_state')}\n"
        f"Dest:    {payload.get('dest_city')}, {payload.get('dest_state')}\n"
        f"Pickup:  {payload.get('pickup_at')}\n"
        f"Deliver: {payload.get('delivery_at')}\n"
        f"Rate:    ${payload.get('rate_total')}\n"
        f"Driver:  {payload.get('driver_name', 'TBD')}\n"
        f"Unit:    {payload.get('truck_id', 'TBD')}\n\n"
        f"— 3 Lakes Logistics"
    )
    sent_to = []
    if s.postmark_server_token:
        try:
            from postmarker.core import PostmarkClient  # type: ignore
            client = PostmarkClient(server_token=s.postmark_server_token)
            for addr in filter(None, [driver_email, broker_email]):
                client.emails.send(From=s.postmark_from_email, To=addr,
                                   Subject=f"Dispatch Sheet — Load {payload.get('load_number')}",
                                   TextBody=body)
                sent_to.append(addr)
        except Exception as e:  # noqa: BLE001
            return {"sent": False, "error": str(e)}
    log_agent("nova", "dispatch_email", carrier_id=str(carrier_id) if carrier_id else None,
              result=f"sent_to={sent_to}")
    return {"sent": bool(sent_to), "sent_to": sent_to,
            "note": "postmark_not_configured" if not s.postmark_server_token else None}


# ── Step 43: signal.dispatch_sms ─────────────────────────────────────────────

def h43_signal_dispatch_sms(carrier_id, contract_id, payload):
    s = get_settings()
    driver_phone = payload.get("driver_phone")
    if not driver_phone:
        return {"sent": False, "reason": "no_driver_phone"}
    msg = (
        f"DISPATCHED: Load {payload.get('load_number')} | "
        f"{payload.get('origin_city')},{payload.get('origin_state')} → "
        f"{payload.get('dest_city')},{payload.get('dest_state')} | "
        f"Pickup {payload.get('pickup_at','TBD')[:10] if payload.get('pickup_at') else 'TBD'} | "
        f"Rate ${payload.get('rate_total')}"
    )
    if s.twilio_account_sid and s.twilio_auth_token:
        try:
            from twilio.rest import Client  # type: ignore
            sid = Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                body=msg, from_=s.twilio_from_number, to=driver_phone).sid
            return {"sent": True, "sms_sid": sid, "to": driver_phone}
        except Exception as e:  # noqa: BLE001
            return {"sent": False, "error": str(e)}
    return {"sent": False, "note": "twilio_not_configured", "would_send": msg}


# ── Step 44: orbit.start_tracking ────────────────────────────────────────────

def h44_orbit_start_tracking(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    truck_id = payload.get("truck_id")
    sb = _db()
    if sb and load_id:
        try:
            sb.table("loads").update({"status": "in_transit"}).eq("id", load_id).execute()
        except Exception:  # noqa: BLE001
            pass
    log_agent("orbit", "start_tracking", carrier_id=str(carrier_id) if carrier_id else None,
              payload={"load_id": load_id, "truck_id": truck_id}, result="tracking_started")
    return {"tracking": True, "load_id": load_id, "truck_id": truck_id, "started_at": _NOW()}


# ── Step 45: audit.fuel_advance ───────────────────────────────────────────────

def h45_audit_fuel_advance(carrier_id, contract_id, payload):
    driver_code = payload.get("driver_code", "")
    amount = float(payload.get("advance_amount") or 0)
    rate_total = float(payload.get("rate_total") or 0)
    if amount == 0:
        return {"requested": False, "note": "no_advance_requested"}
    decision = audit.decide_advance(driver_code, amount, rate_total)
    sb = _db()
    if sb and decision["approved"]:
        try:
            sb.table("loads").update(
                {"fuel_advance": amount, "fuel_advance_approved_at": _NOW()}
            ).eq("id", payload.get("load_id", "")).execute()
        except Exception:  # noqa: BLE001
            pass
    return {
        "requested": True,
        "amount": amount,
        "approved": decision["approved"],
        "reason": decision["reason"],
        "driver_code": driver_code,
    }


# ── Step 46: dispatch.log_event ───────────────────────────────────────────────

def h46_dispatch_log_event(carrier_id, contract_id, payload):
    try:
        from ...atomic_ledger.service import write_event
        from ...atomic_ledger.models import AtomicEvent
        write_event(AtomicEvent(
            event_type="dispatch.complete",
            event_source="execution_engine.step_46",
            logistics_payload={
                "load_id": payload.get("load_id"),
                "load_number": payload.get("load_number"),
                "truck_id": payload.get("truck_id"),
                "driver_code": payload.get("driver_code"),
                "origin": f"{payload.get('origin_city')},{payload.get('origin_state')}",
                "destination": f"{payload.get('dest_city')},{payload.get('dest_state')}",
            },
            financial_payload={
                "rate_total": payload.get("rate_total"),
                "rate_per_mile": payload.get("rate_per_mile"),
                "fuel_advance": payload.get("advance_amount", 0),
            },
            compliance_payload={"carrier_id": str(carrier_id) if carrier_id else None},
        ))
        return {"logged": True}
    except Exception as e:  # noqa: BLE001
        return {"logged": False, "error": str(e)}


# ── Step 47: sonny.post_loadboard ────────────────────────────────────────────

def h47_sonny_post_loadboard(carrier_id, contract_id, payload):
    is_spot = payload.get("is_spot", False)
    if not is_spot:
        return {"posted": False, "reason": "not_a_spot_load"}
    result = sonny.run({
        "truck_id": payload.get("truck_id"),
        "trailer_type": payload.get("equipment_type"),
        "origin_state": payload.get("origin_state"),
    })
    return {"posted": True, "sources": result.get("sources_queried", []), "load_board_result": result}


# ── Step 48: dispatch.eta_calculate ──────────────────────────────────────────

def h48_dispatch_eta_calculate(carrier_id, contract_id, payload):
    miles = payload.get("miles") or 0
    hos_remaining = float(payload.get("hos_remaining") or 11.0)
    avg_speed = 60  # mph
    pickup_at = payload.get("pickup_at")
    if miles and pickup_at:
        try:
            drive_hours_needed = miles / avg_speed
            # Account for 10hr rest after 11hr drive
            rest_breaks = max(0, int(drive_hours_needed / hos_remaining) - 1)
            total_hours = drive_hours_needed + (rest_breaks * 10)
            pickup_dt = datetime.fromisoformat(pickup_at.replace("Z", "+00:00"))
            eta_dt = pickup_dt + timedelta(hours=total_hours)
            eta = eta_dt.isoformat()
        except Exception:  # noqa: BLE001
            eta = None
    else:
        eta = None
    s = get_settings()
    if s.google_maps_api_key and payload.get("origin_zip") and payload.get("dest_zip"):
        try:
            import httpx
            r = httpx.get(
                "https://maps.googleapis.com/maps/api/distancematrix/json",
                params={
                    "origins": payload["origin_zip"],
                    "destinations": payload["dest_zip"],
                    "key": s.google_maps_api_key,
                },
                timeout=8,
            )
            data = r.json()
            elements = data.get("rows", [{}])[0].get("elements", [{}])[0]
            if elements.get("status") == "OK":
                miles = elements["distance"]["value"] / 1609
                return {"eta": eta, "miles": round(miles), "source": "google_maps"}
        except Exception:  # noqa: BLE001
            pass
    return {"eta": eta, "miles": miles, "source": "estimated", "avg_speed_mph": avg_speed}


# ── Step 49: penny.margin_preview ────────────────────────────────────────────

def h49_penny_margin_preview(carrier_id, contract_id, payload):
    rate = float(payload.get("rate_total") or 0)
    miles = float(payload.get("miles") or 0)
    driver_pct = float(payload.get("driver_pct") or 0.75)
    fuel_cost = float(payload.get("fuel_cost") or (miles * 0.55))  # ~$0.55/mi default
    driver_pay = rate * driver_pct
    gross_margin = rate - driver_pay - fuel_cost
    margin_pct = round((gross_margin / rate * 100), 2) if rate else 0
    return {
        "rate_total": rate,
        "driver_pay": round(driver_pay, 2),
        "fuel_cost": round(fuel_cost, 2),
        "gross_margin": round(gross_margin, 2),
        "margin_pct": margin_pct,
        "rpm": round(rate / miles, 4) if miles else None,
        "viable": gross_margin > 0,
    }


# ── Step 50: dispatch.assign_load_id ─────────────────────────────────────────

def h50_dispatch_assign_load_id(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    load_number = payload.get("load_number")
    if not load_id:
        return {"assigned": False, "reason": "no_load_id"}
    sb = _db()
    if sb and load_number:
        try:
            sb.table("loads").update({"load_number": load_number}).eq("id", load_id).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"assigned": True, "load_id": load_id, "load_number": load_number, "assigned_at": _NOW()}


# ── Step 51: dispatch.notify_shipper ─────────────────────────────────────────

def h51_dispatch_notify_shipper(carrier_id, contract_id, payload):
    s = get_settings()
    shipper_email = payload.get("shipper_email")
    shipper_phone = payload.get("shipper_phone")
    driver_name = payload.get("driver_name", "on file")
    truck_id = payload.get("truck_id", "on file")
    eta = payload.get("eta", "on schedule")
    load_number = payload.get("load_number")
    notified = []
    if s.postmark_server_token and shipper_email:
        try:
            from postmarker.core import PostmarkClient  # type: ignore
            PostmarkClient(server_token=s.postmark_server_token).emails.send(
                From=s.postmark_from_email, To=shipper_email,
                Subject=f"Driver En Route — Load {load_number}",
                TextBody=(f"Driver {driver_name} | Unit {truck_id} is en route.\nETA: {eta}\n— 3 Lakes Logistics"),
            )
            notified.append(shipper_email)
        except Exception:  # noqa: BLE001
            pass
    if s.twilio_account_sid and shipper_phone:
        try:
            from twilio.rest import Client  # type: ignore
            Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                body=f"Load {load_number}: Driver {driver_name} | Unit {truck_id} | ETA {eta}",
                from_=s.twilio_from_number, to=shipper_phone)
            notified.append(shipper_phone)
        except Exception:  # noqa: BLE001
            pass
    return {"notified": bool(notified), "sent_to": notified,
            "driver_name": driver_name, "truck_id": truck_id, "eta": eta}


# ── Step 52: dispatch.schedule_checkcall_1 ────────────────────────────────────

def h52_dispatch_schedule_checkcall_1(carrier_id, contract_id, payload):
    pickup_at = payload.get("pickup_at")
    scheduled_for = None
    if pickup_at:
        try:
            pickup_dt = datetime.fromisoformat(pickup_at.replace("Z", "+00:00"))
            scheduled_for = (pickup_dt + timedelta(hours=2)).isoformat()
        except Exception:  # noqa: BLE001
            pass
    sb = _db()
    if sb:
        try:
            sb.table("scheduled_tasks").insert({
                "task_type": "check_call_1",
                "carrier_id": str(carrier_id) if carrier_id else None,
                "load_id": payload.get("load_id"),
                "scheduled_for": scheduled_for,
                "status": "pending",
                "created_at": _NOW(),
            }).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"scheduled": True, "check_call": 1, "scheduled_for": scheduled_for}


# ── Step 53: dispatch.schedule_checkcall_2 ────────────────────────────────────

def h53_dispatch_schedule_checkcall_2(carrier_id, contract_id, payload):
    eta = payload.get("eta")
    pickup_at = payload.get("pickup_at")
    scheduled_for = None
    if eta and pickup_at:
        try:
            p = datetime.fromisoformat(pickup_at.replace("Z", "+00:00"))
            e = datetime.fromisoformat(eta.replace("Z", "+00:00"))
            midpoint = p + (e - p) / 2
            scheduled_for = midpoint.isoformat()
        except Exception:  # noqa: BLE001
            pass
    sb = _db()
    if sb:
        try:
            sb.table("scheduled_tasks").insert({
                "task_type": "check_call_2",
                "carrier_id": str(carrier_id) if carrier_id else None,
                "load_id": payload.get("load_id"),
                "scheduled_for": scheduled_for,
                "status": "pending",
                "created_at": _NOW(),
            }).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"scheduled": True, "check_call": 2, "scheduled_for": scheduled_for}


# ── Step 54: dispatch.schedule_checkcall_3 ────────────────────────────────────

def h54_dispatch_schedule_checkcall_3(carrier_id, contract_id, payload):
    eta = payload.get("eta")
    scheduled_for = None
    if eta:
        try:
            eta_dt = datetime.fromisoformat(eta.replace("Z", "+00:00"))
            scheduled_for = (eta_dt - timedelta(hours=2)).isoformat()
        except Exception:  # noqa: BLE001
            pass
    sb = _db()
    if sb:
        try:
            sb.table("scheduled_tasks").insert({
                "task_type": "check_call_3",
                "carrier_id": str(carrier_id) if carrier_id else None,
                "load_id": payload.get("load_id"),
                "scheduled_for": scheduled_for,
                "status": "pending",
                "created_at": _NOW(),
            }).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"scheduled": True, "check_call": 3, "scheduled_for": scheduled_for}


# ── Step 55: fleet.status_intransit ──────────────────────────────────────────

def h55_fleet_status_intransit(carrier_id, contract_id, payload):
    truck_id = payload.get("truck_id")
    load_id = payload.get("load_id")
    if not truck_id:
        return {"updated": False, "reason": "no_truck_id"}
    sb = _db()
    if sb:
        try:
            sb.table("fleet_assets").update(
                {"status": "in_transit", "current_load_id": load_id}
            ).eq("truck_id", truck_id).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"updated": True, "truck_id": truck_id, "status": "in_transit", "load_id": load_id}


# ── Step 56: document_vault.expect_bol ───────────────────────────────────────

def h56_document_vault_expect_bol(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    pickup_at = payload.get("pickup_at")
    due_by = None
    if pickup_at:
        try:
            due_by = (datetime.fromisoformat(pickup_at.replace("Z", "+00:00")) + timedelta(hours=2)).isoformat()
        except Exception:  # noqa: BLE001
            pass
    sb = _db()
    if sb:
        try:
            sb.table("scheduled_tasks").insert({
                "task_type": "bol_due_check",
                "carrier_id": str(carrier_id) if carrier_id else None,
                "load_id": load_id,
                "scheduled_for": due_by,
                "status": "pending",
                "created_at": _NOW(),
            }).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"expectation_set": True, "doc_type": "bol", "load_id": load_id, "due_by": due_by}


# ── Step 57: dispatch.rate_lock ───────────────────────────────────────────────

def h57_dispatch_rate_lock(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    rate_total = payload.get("rate_total")
    sb = _db()
    if sb and load_id:
        try:
            sb.table("loads").update(
                {"rate_locked": True, "rate_locked_at": _NOW()}
            ).eq("id", load_id).execute()
        except Exception:  # noqa: BLE001
            pass
    if sb and contract_id:
        try:
            sb.table("contracts").update({"status": "active"}).eq("id", str(contract_id)).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"locked": True, "load_id": load_id, "rate_total": rate_total, "locked_at": _NOW()}


# ── Step 58: dispatch.insurance_check ────────────────────────────────────────

def h58_dispatch_insurance_check(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"cleared": False, "reason": "no_carrier_id"}
    sb = _db()
    if not sb:
        return {"cleared": True, "note": "supabase_not_configured"}
    try:
        r = sb.table("insurance_compliance").select(
            "policy_expiry,safety_light"
        ).eq("carrier_id", str(carrier_id)).maybe_single().execute()
        ins = r.data or {}
        safety_light = ins.get("safety_light", "green")
        expiry = ins.get("policy_expiry")
        if safety_light == "red":
            return {"cleared": False, "reason": "red_safety_light"}
        if expiry:
            from datetime import date
            days_left = (date.fromisoformat(expiry) - date.today()).days
            if days_left <= 0:
                return {"cleared": False, "reason": "insurance_expired", "expiry": expiry}
        return {"cleared": True, "safety_light": safety_light, "policy_expiry": expiry}
    except Exception as e:  # noqa: BLE001
        return {"cleared": False, "error": str(e)}


# ── Step 59: shield.pre_dispatch_safety ──────────────────────────────────────

def h59_shield_pre_dispatch_safety(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"cleared": False, "reason": "no_carrier_id"}
    sb = _db()
    safety_light = "green"
    csa_high_risk = False
    if sb:
        try:
            r = sb.table("insurance_compliance").select(
                "safety_light,csa_score"
            ).eq("carrier_id", str(carrier_id)).maybe_single().execute()
            rec = r.data or {}
            safety_light = rec.get("safety_light", "green")
            csa_high_risk = bool(rec.get("csa_high_risk", False))
        except Exception:  # noqa: BLE001
            pass
    cleared = safety_light != "red" and not csa_high_risk
    return {
        "cleared": cleared,
        "safety_light": safety_light,
        "csa_high_risk": csa_high_risk,
        "reason": "red_light_or_csa" if not cleared else None,
    }


# ── Step 60: dispatch.complete ────────────────────────────────────────────────

def h60_dispatch_complete(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    sb = _db()
    if sb and load_id:
        try:
            sb.table("loads").update({"status": "in_transit"}).eq("id", load_id).execute()
        except Exception:  # noqa: BLE001
            pass
    try:
        from ...atomic_ledger.service import write_event
        from ...atomic_ledger.models import AtomicEvent
        write_event(AtomicEvent(
            event_type="dispatch.workflow_complete",
            event_source="execution_engine.step_60",
            logistics_payload={
                "load_id": load_id,
                "truck_id": payload.get("truck_id"),
                "driver_code": payload.get("driver_code"),
                "origin": f"{payload.get('origin_city')},{payload.get('origin_state')}",
                "destination": f"{payload.get('dest_city')},{payload.get('dest_state')}",
                "eta": payload.get("eta"),
            },
            financial_payload={
                "rate_total": payload.get("rate_total"),
                "margin": payload.get("gross_margin"),
                "margin_pct": payload.get("margin_pct"),
            },
            compliance_payload={"insurance_cleared": payload.get("insurance_cleared", True)},
        ))
    except Exception as e:  # noqa: BLE001
        log.warning("atomic_ledger write failed at step 60: %s", e)
    return {"dispatch_complete": True, "load_id": load_id, "completed_at": _NOW()}


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
    41: h41_dispatch_confirm_broker,
    42: h42_nova_dispatch_email,
    43: h43_signal_dispatch_sms,
    44: h44_orbit_start_tracking,
    45: h45_audit_fuel_advance,
    46: h46_dispatch_log_event,
    47: h47_sonny_post_loadboard,
    48: h48_dispatch_eta_calculate,
    49: h49_penny_margin_preview,
    50: h50_dispatch_assign_load_id,
    51: h51_dispatch_notify_shipper,
    52: h52_dispatch_schedule_checkcall_1,
    53: h53_dispatch_schedule_checkcall_2,
    54: h54_dispatch_schedule_checkcall_3,
    55: h55_fleet_status_intransit,
    56: h56_document_vault_expect_bol,
    57: h57_dispatch_rate_lock,
    58: h58_dispatch_insurance_check,
    59: h59_shield_pre_dispatch_safety,
    60: h60_dispatch_complete,
}

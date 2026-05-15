"""Phase 3 — In-Transit Operations handlers (steps 61–90)."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from ...agents import scout, signal, orbit, atlas, pulse, vance
from ...logging_service import get_logger, log_agent
from ...settings import get_settings

log = get_logger("3ll.execution.transit")

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _db():
    try:
        from ...supabase_client import get_supabase
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


# ── Step 61: transit.pickup_confirmed ────────────────────────────────────────

def h61_transit_pickup_confirmed(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    truck_id = payload.get("truck_id")
    sb = _db()
    if sb and load_id:
        try:
            sb.table("loads").update({
                "status": "in_transit",
                "pickup_confirmed_at": _NOW(),
            }).eq("id", load_id).execute()
        except Exception:  # noqa: BLE001
            pass
    if sb and contract_id:
        try:
            sb.table("contracts").update({"milestone_pct": 50}).eq("id", str(contract_id)).execute()
        except Exception:  # noqa: BLE001
            pass
    log_agent("orbit", "pickup_confirmed", carrier_id=str(carrier_id) if carrier_id else None,
              payload={"load_id": load_id, "truck_id": truck_id}, result="confirmed")
    return {"confirmed": True, "load_id": load_id, "truck_id": truck_id,
            "confirmed_at": _NOW(), "milestone_pct": 50}


# ── Step 62: document_vault.upload_bol ───────────────────────────────────────

def h62_document_vault_upload_bol(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    bol_url = payload.get("bol_url") or payload.get("doc_url")
    sb = _db()
    if not sb:
        return {"uploaded": False, "note": "supabase_not_configured"}
    try:
        sb.table("document_vault").insert({
            "carrier_id": str(carrier_id) if carrier_id else None,
            "contract_id": str(contract_id) if contract_id else None,
            "doc_type": "bol",
            "filename": f"bol_{load_id}.pdf" if load_id else "bol.pdf",
            "storage_path": bol_url or f"loads/{load_id}/bol.pdf",
            "scan_status": "pending",
        }).execute()
        return {"uploaded": True, "load_id": load_id, "bol_url": bol_url}
    except Exception as e:  # noqa: BLE001
        return {"uploaded": False, "error": str(e)}


# ── Step 63: scout.extract_bol ───────────────────────────────────────────────

def h63_scout_extract_bol(carrier_id, contract_id, payload):
    raw_text = payload.get("raw_text") or payload.get("bol_text")
    s = get_settings()
    if not raw_text:
        extracted = scout.ocr_document(None)
        return {"extracted": extracted, "confidence": 0.0, "note": "no_raw_text"}
    if not s.anthropic_api_key:
        extracted = scout.ocr_document(None)
        return {"extracted": extracted, "confidence": 0.0, "note": "anthropic_not_configured"}
    try:
        from ...clm.scanner import scan_contract
        extracted, confidence, warnings = scan_contract(raw_text, "bol")
        log_agent("scout", "extract_bol", carrier_id=str(carrier_id) if carrier_id else None,
                  result=f"confidence={confidence}")
        return {"extracted": extracted, "confidence": confidence, "warnings": warnings}
    except Exception as e:  # noqa: BLE001
        return {"extracted": {}, "confidence": 0.0, "error": str(e)}


# ── Step 64: clm.link_bol_to_contract ────────────────────────────────────────

def h64_clm_link_bol_to_contract(carrier_id, contract_id, payload):
    if not contract_id:
        return {"linked": False, "reason": "no_contract_id"}
    extracted = payload.get("extracted") or {}
    sb = _db()
    if not sb:
        return {"linked": False, "note": "supabase_not_configured"}
    try:
        sb.table("contracts").update({
            "extracted_vars": {
                **(payload.get("existing_vars") or {}),
                "bol": extracted,
            },
            "milestone_pct": 50,
            "updated_at": _NOW(),
        }).eq("id", str(contract_id)).execute()
        sb.table("contract_events").insert({
            "contract_id": str(contract_id),
            "event_type": "bol_linked",
            "actor": "execution_engine",
            "payload": {"bol_number": extracted.get("bol_number")},
        }).execute()
        return {"linked": True, "contract_id": str(contract_id),
                "bol_number": extracted.get("bol_number")}
    except Exception as e:  # noqa: BLE001
        return {"linked": False, "error": str(e)}


# ── Step 65: orbit.gps_ping_loop ─────────────────────────────────────────────

def h65_orbit_gps_ping_loop(carrier_id, contract_id, payload):
    truck_id = payload.get("truck_id")
    lat = payload.get("lat")
    lng = payload.get("lng")
    sb = _db()
    if sb and truck_id and lat and lng:
        try:
            sb.table("truck_telemetry").insert({
                "carrier_id": str(carrier_id) if carrier_id else None,
                "truck_id": truck_id,
                "lat": lat,
                "lng": lng,
                "speed": payload.get("speed"),
                "heading": payload.get("heading"),
                "ts": _NOW(),
            }).execute()
        except Exception:  # noqa: BLE001
            pass
    log_agent("orbit", "gps_ping", carrier_id=str(carrier_id) if carrier_id else None,
              payload={"truck_id": truck_id, "lat": lat, "lng": lng}, result="pinged")
    return {"pinged": True, "truck_id": truck_id, "lat": lat, "lng": lng, "ts": _NOW()}


# ── Step 66: pulse.hos_monitor ───────────────────────────────────────────────

def h66_pulse_hos_monitor(carrier_id, contract_id, payload):
    driver_code = payload.get("driver_code")
    sb = _db()
    drive_remaining = None
    if sb and driver_code:
        try:
            r = sb.table("driver_hos_status").select(
                "drive_remaining,shift_remaining,cycle_remaining"
            ).eq("driver_id", driver_code).maybe_single().execute()
            rec = r.data or {}
            drive_remaining = rec.get("drive_remaining")
        except Exception:  # noqa: BLE001
            pass
    drive_remaining = drive_remaining or payload.get("drive_remaining", 11.0)
    warning = float(drive_remaining) <= 2.0
    return {
        "driver_code": driver_code,
        "drive_remaining_hrs": drive_remaining,
        "warning": warning,
        "alert_level": "urgent" if float(drive_remaining) <= 1.0 else ("warning" if warning else "ok"),
    }


# ── Step 67: signal.hos_warning ──────────────────────────────────────────────

def h67_signal_hos_warning(carrier_id, contract_id, payload):
    drive_remaining = float(payload.get("drive_remaining_hrs") or 11.0)
    if drive_remaining > 2.0:
        return {"sent": False, "reason": "hos_within_limits"}
    s = get_settings()
    driver_phone = payload.get("driver_phone")
    commander_phone = payload.get("commander_number")
    msg = (f"HOS WARNING: Driver {payload.get('driver_code','unknown')} has "
           f"{drive_remaining:.1f}hrs remaining. Load {payload.get('load_id','')}")
    sent = []
    if s.twilio_account_sid and s.twilio_auth_token:
        try:
            from twilio.rest import Client  # type: ignore
            client = Client(s.twilio_account_sid, s.twilio_auth_token)
            for phone in filter(None, [driver_phone, commander_phone]):
                client.messages.create(body=msg, from_=s.twilio_from_number, to=phone)
                sent.append(phone)
        except Exception:  # noqa: BLE001
            pass
    return {"sent": bool(sent), "sent_to": sent, "hrs_remaining": drive_remaining,
            "note": "twilio_not_configured" if not s.twilio_account_sid else None}


# ── Step 68: atlas.checkcall_1 ───────────────────────────────────────────────

def h68_atlas_checkcall_1(carrier_id, contract_id, payload):
    phone = payload.get("driver_phone") or payload.get("broker_phone")
    if not phone:
        return {"called": False, "reason": "no_phone"}
    s = get_settings()
    if s.vapi_api_key:
        result = vance.start_outbound_call(
            str(carrier_id) if carrier_id else "",
            phone,
            {"script": "check_call_1", "load_id": payload.get("load_id"),
             "load_number": payload.get("load_number")},
        )
        return {"called": result.get("status") == "started", "check_call": 1, **result}
    return {"called": False, "check_call": 1, "note": "vapi_not_configured",
            "would_call": phone, "load_id": payload.get("load_id")}


# ── Step 69: atlas.checkcall_2 ───────────────────────────────────────────────

def h69_atlas_checkcall_2(carrier_id, contract_id, payload):
    phone = payload.get("driver_phone") or payload.get("broker_phone")
    if not phone:
        return {"called": False, "reason": "no_phone"}
    s = get_settings()
    if s.vapi_api_key:
        result = vance.start_outbound_call(
            str(carrier_id) if carrier_id else "",
            phone,
            {"script": "check_call_2", "load_id": payload.get("load_id"),
             "current_location": payload.get("current_location"),
             "eta": payload.get("eta")},
        )
        return {"called": result.get("status") == "started", "check_call": 2, **result}
    return {"called": False, "check_call": 2, "note": "vapi_not_configured",
            "would_call": phone}


# ── Step 70: signal.delay_alert ──────────────────────────────────────────────

def h70_signal_delay_alert(carrier_id, contract_id, payload):
    original_eta = payload.get("original_eta")
    current_eta = payload.get("eta") or payload.get("current_eta")
    if not original_eta or not current_eta:
        return {"alerted": False, "reason": "missing_eta_data"}
    try:
        orig = datetime.fromisoformat(original_eta.replace("Z", "+00:00"))
        curr = datetime.fromisoformat(current_eta.replace("Z", "+00:00"))
        slip_hrs = (curr - orig).total_seconds() / 3600
    except Exception:  # noqa: BLE001
        return {"alerted": False, "reason": "bad_eta_format"}
    if slip_hrs < 2.0:
        return {"alerted": False, "slip_hrs": round(slip_hrs, 2), "within_threshold": True}
    s = get_settings()
    msg = (f"ETA DELAY: Load {payload.get('load_number')} slipped "
           f"{slip_hrs:.1f}hrs. New ETA: {current_eta[:16]}")
    sent = []
    if s.twilio_account_sid and s.twilio_auth_token:
        try:
            from twilio.rest import Client  # type: ignore
            client = Client(s.twilio_account_sid, s.twilio_auth_token)
            for phone in filter(None, [payload.get("broker_phone"), payload.get("shipper_phone")]):
                client.messages.create(body=msg, from_=s.twilio_from_number, to=phone)
                sent.append(phone)
        except Exception:  # noqa: BLE001
            pass
    return {"alerted": True, "slip_hrs": round(slip_hrs, 2), "sent_to": sent,
            "note": "twilio_not_configured" if not s.twilio_account_sid else None}


# ── Step 71: orbit.geofence_delivery ─────────────────────────────────────────

def h71_orbit_geofence_delivery(carrier_id, contract_id, payload):
    lat = payload.get("lat")
    lng = payload.get("lng")
    fence_lat = payload.get("dest_lat") or payload.get("fence_lat")
    fence_lng = payload.get("dest_lng") or payload.get("fence_lng")
    if not all([lat, lng, fence_lat, fence_lng]):
        return {"arrived": False, "reason": "missing_coordinates"}
    arrived = orbit.inside_fence(float(lat), float(lng), float(fence_lat), float(fence_lng))
    if arrived:
        sb = _db()
        if sb and payload.get("load_id"):
            try:
                sb.table("loads").update(
                    {"delivery_geofence_entered_at": _NOW()}
                ).eq("id", payload["load_id"]).execute()
            except Exception:  # noqa: BLE001
                pass
    return {"arrived": arrived, "lat": lat, "lng": lng, "load_id": payload.get("load_id")}


# ── Step 72: atlas.checkcall_3 ───────────────────────────────────────────────

def h72_atlas_checkcall_3(carrier_id, contract_id, payload):
    phone = payload.get("driver_phone") or payload.get("broker_phone")
    if not phone:
        return {"called": False, "reason": "no_phone"}
    s = get_settings()
    if s.vapi_api_key:
        result = vance.start_outbound_call(
            str(carrier_id) if carrier_id else "",
            phone,
            {"script": "check_call_3", "load_id": payload.get("load_id"),
             "eta": payload.get("eta")},
        )
        return {"called": result.get("status") == "started", "check_call": 3, **result}
    return {"called": False, "check_call": 3, "note": "vapi_not_configured",
            "would_call": phone}


# ── Step 73: transit.weather_check ───────────────────────────────────────────

def h73_transit_weather_check(carrier_id, contract_id, payload):
    origin_state = payload.get("origin_state")
    dest_state = payload.get("dest_state")
    origin_lat = payload.get("origin_lat")
    origin_lon = payload.get("origin_lon")
    dest_lat = payload.get("dest_lat")
    dest_lon = payload.get("dest_lon")
    s = get_settings()

    risk = "low"
    delays_possible = False
    weather_alerts = []

    if origin_lat and origin_lon:
        try:
            import httpx
            # Use Open-Meteo free weather API (no key required, no rate limits)
            r = httpx.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": origin_lat,
                    "longitude": origin_lon,
                    "current": "weather_code,temperature,wind_speed,precipitation",
                    "hourly": "precipitation_probability",
                    "timezone": "auto",
                },
                timeout=8,
            )
            data = r.json()
            current = data.get("current", {})
            weather_code = current.get("weather_code", 0)
            wind_speed = current.get("wind_speed", 0)
            precipitation = current.get("precipitation", 0)

            # WMO Weather Code interpretation
            # 80-82: Rain showers (heavy)
            # 71-75: Snow
            # 55-56: Freezing rain/drizzle
            # 40-49: Fog
            # 61-67: Rain
            if weather_code >= 80:
                risk = "high"
                delays_possible = True
                weather_alerts.append(f"Heavy rain (code {weather_code})")
            elif weather_code >= 71:
                risk = "high"
                delays_possible = True
                weather_alerts.append(f"Snow (code {weather_code})")
            elif weather_code >= 55:
                risk = "medium"
                delays_possible = True
                weather_alerts.append(f"Freezing precipitation (code {weather_code})")
            elif weather_code >= 40:
                risk = "medium"
                weather_alerts.append(f"Fog (code {weather_code})")
            elif weather_code >= 61:
                risk = "low"
                delays_possible = False
                weather_alerts.append(f"Rain (code {weather_code})")

            if wind_speed > 50:
                risk = "high"
                delays_possible = True
                weather_alerts.append(f"High winds ({wind_speed} km/h)")
            elif wind_speed > 35:
                risk = "medium"
                weather_alerts.append(f"Strong winds ({wind_speed} km/h)")

        except Exception as e:
            log.warning("weather_check API failed: %s", e)

    return {
        "checked": True,
        "origin_state": origin_state,
        "dest_state": dest_state,
        "risk": risk,
        "delays_possible": delays_possible,
        "alerts": weather_alerts,
        "note": "weather checked via open-meteo api" if weather_alerts else "clear weather",
    }


# ── Step 74: transit.traffic_check ───────────────────────────────────────────

def h74_transit_traffic_check(carrier_id, contract_id, payload):
    miles = payload.get("miles", 0)
    original_eta = payload.get("eta")
    s = get_settings()
    delay_mins = 0
    updated_eta = original_eta
    if s.google_maps_api_key and payload.get("origin_zip") and payload.get("dest_zip"):
        try:
            import httpx
            r = httpx.get(
                "https://maps.googleapis.com/maps/api/distancematrix/json",
                params={
                    "origins": payload["origin_zip"],
                    "destinations": payload["dest_zip"],
                    "departure_time": "now",
                    "key": s.google_maps_api_key,
                },
                timeout=8,
            )
            el = r.json().get("rows", [{}])[0].get("elements", [{}])[0]
            if el.get("status") == "OK":
                normal_secs = el.get("duration", {}).get("value", 0)
                traffic_secs = el.get("duration_in_traffic", {}).get("value", normal_secs)
                delay_mins = max(0, (traffic_secs - normal_secs) // 60)
                if original_eta and delay_mins > 0:
                    try:
                        eta_dt = datetime.fromisoformat(original_eta.replace("Z", "+00:00"))
                        updated_eta = (eta_dt + timedelta(minutes=delay_mins)).isoformat()
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass
    return {"checked": True, "delay_mins": delay_mins, "updated_eta": updated_eta,
            "eta_changed": updated_eta != original_eta}


# ── Step 75: signal.breakdown_detect ─────────────────────────────────────────

def h75_signal_breakdown_detect(carrier_id, contract_id, payload):
    truck_id = payload.get("truck_id")
    speed = float(payload.get("speed") or 0)
    minutes_stopped = float(payload.get("minutes_stopped") or 0)
    off_route = payload.get("off_route", False)
    breakdown = speed == 0 and minutes_stopped >= 30 and off_route
    return {
        "breakdown_detected": breakdown,
        "truck_id": truck_id,
        "speed": speed,
        "minutes_stopped": minutes_stopped,
        "off_route": off_route,
    }


# ── Step 76: signal.emergency_escalate ───────────────────────────────────────

def h76_signal_emergency_escalate(carrier_id, contract_id, payload):
    if not payload.get("breakdown_detected", False):
        return {"escalated": False, "reason": "no_breakdown_detected"}
    s = get_settings()
    msg = (f"BREAKDOWN ALERT: Truck {payload.get('truck_id')} — "
           f"load {payload.get('load_id')} — stopped {payload.get('minutes_stopped',0):.0f}min off-route. "
           f"Location: {payload.get('lat')},{payload.get('lng')}")
    if s.twilio_account_sid and s.twilio_auth_token:
        try:
            from twilio.rest import Client  # type: ignore
            Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                body=msg, from_=s.twilio_from_number,
                to=payload.get("commander_number", s.twilio_from_number))
            return {"escalated": True, "message": msg}
        except Exception as e:  # noqa: BLE001
            return {"escalated": False, "error": str(e)}
    return {"escalated": False, "note": "twilio_not_configured", "would_send": msg}


# ── Step 77: transit.detention_clock ─────────────────────────────────────────

def h77_transit_detention_clock(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    arrived_at = payload.get("arrived_at") or payload.get("confirmed_at") or _NOW()
    sb = _db()
    if sb and load_id:
        try:
            sb.table("loads").update(
                {"shipper_arrived_at": arrived_at, "detention_clock_started": True}
            ).eq("id", load_id).execute()
        except Exception:  # noqa: BLE001
            pass
    free_time_end = None
    try:
        arr_dt = datetime.fromisoformat(arrived_at.replace("Z", "+00:00"))
        free_time_end = (arr_dt + timedelta(hours=2)).isoformat()
    except Exception:  # noqa: BLE001
        pass
    return {"clock_started": True, "load_id": load_id,
            "arrived_at": arrived_at, "free_time_ends": free_time_end}


# ── Step 78: transit.detention_notify ────────────────────────────────────────

def h78_transit_detention_notify(carrier_id, contract_id, payload):
    free_time_end = payload.get("free_time_ends")
    if not free_time_end:
        return {"notified": False, "reason": "no_free_time_end"}
    try:
        fte_dt = datetime.fromisoformat(free_time_end.replace("Z", "+00:00"))
        now_dt = datetime.now(timezone.utc)
        in_detention = now_dt > fte_dt
        hours_detained = max(0, (now_dt - fte_dt).total_seconds() / 3600)
    except Exception:  # noqa: BLE001
        in_detention = False
        hours_detained = 0
    if not in_detention:
        return {"notified": False, "reason": "still_within_free_time"}
    s = get_settings()
    rate = payload.get("detention_rate", 75)
    accrued = round(hours_detained * rate, 2)
    msg = (f"DETENTION: Load {payload.get('load_number')} — "
           f"{hours_detained:.1f}hrs @ ${rate}/hr = ${accrued} accrued")
    sent = []
    if s.twilio_account_sid and s.twilio_auth_token:
        try:
            from twilio.rest import Client  # type: ignore
            client = Client(s.twilio_account_sid, s.twilio_auth_token)
            for phone in filter(None, [payload.get("broker_phone")]):
                client.messages.create(body=msg, from_=s.twilio_from_number, to=phone)
                sent.append(phone)
        except Exception:  # noqa: BLE001
            pass
    return {"notified": True, "in_detention": True, "hours_detained": round(hours_detained, 2),
            "rate_per_hr": rate, "accrued": accrued, "sent_to": sent}


# ── Step 79: transit.lumper_approve ──────────────────────────────────────────

def h79_transit_lumper_approve(carrier_id, contract_id, payload):
    amount = float(payload.get("lumper_amount") or 0)
    receipt_url = payload.get("receipt_url")
    if amount == 0:
        return {"approved": False, "reason": "no_lumper_amount"}
    max_lumper = 500
    approved = amount <= max_lumper
    sb = _db()
    if sb and approved and payload.get("load_id"):
        try:
            sb.table("loads").update({
                "lumper_amount": amount,
                "lumper_receipt_url": receipt_url,
                "lumper_approved_at": _NOW(),
            }).eq("id", payload["load_id"]).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"approved": approved, "amount": amount, "receipt_url": receipt_url,
            "reason": f"exceeds_${max_lumper}_cap" if not approved else None}


# ── Step 80: penny.fuel_cost_track ───────────────────────────────────────────

def h80_penny_fuel_cost_track(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    fuel_amount = float(payload.get("fuel_amount") or 0)
    gallons = float(payload.get("gallons") or 0)
    location = payload.get("fuel_location")
    sb = _db()
    if sb and load_id and fuel_amount:
        try:
            sb.table("loads").update({
                "fuel_cost": fuel_amount,
                "fuel_gallons": gallons,
            }).eq("id", load_id).execute()
        except Exception:  # noqa: BLE001
            pass
    log_agent("penny", "fuel_cost_track", carrier_id=str(carrier_id) if carrier_id else None,
              payload={"load_id": load_id, "amount": fuel_amount}, result="tracked")
    return {"tracked": True, "load_id": load_id, "fuel_amount": fuel_amount,
            "gallons": gallons, "location": location}


# ── Step 81: transit.mid_route_safety ────────────────────────────────────────

def h81_transit_mid_route_safety(carrier_id, contract_id, payload):
    if not carrier_id:
        return {"cleared": True, "note": "no_carrier_id"}
    sb = _db()
    if not sb:
        return {"cleared": True, "note": "supabase_not_configured"}
    try:
        r = sb.table("insurance_compliance").select(
            "safety_light,csa_high_risk,policy_expiry"
        ).eq("carrier_id", str(carrier_id)).maybe_single().execute()
        rec = r.data or {}
        light = rec.get("safety_light", "green")
        cleared = light != "red"
        return {"cleared": cleared, "safety_light": light,
                "csa_high_risk": rec.get("csa_high_risk", False),
                "policy_expiry": rec.get("policy_expiry")}
    except Exception as e:  # noqa: BLE001
        return {"cleared": True, "error": str(e)}


# ── Step 82: transit.broker_visibility ───────────────────────────────────────

def h82_transit_broker_visibility(carrier_id, contract_id, payload):
    lat = payload.get("lat")
    lng = payload.get("lng")
    truck_id = payload.get("truck_id")
    load_id = payload.get("load_id")
    sb = _db()
    if sb and load_id:
        try:
            sb.table("loads").update({
                "last_lat": lat, "last_lng": lng, "last_location_at": _NOW()
            }).eq("id", load_id).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"pushed": True, "truck_id": truck_id, "load_id": load_id,
            "lat": lat, "lng": lng, "pushed_at": _NOW()}


# ── Step 83: transit.eta_sms_update ──────────────────────────────────────────

def h83_transit_eta_sms_update(carrier_id, contract_id, payload):
    consignee_phone = payload.get("consignee_phone")
    eta = payload.get("eta") or payload.get("updated_eta")
    if not consignee_phone:
        return {"sent": False, "reason": "no_consignee_phone"}
    s = get_settings()
    msg = (f"Delivery Update: Load {payload.get('load_number')} — "
           f"ETA {eta[:16] if eta else 'TBD'}. Driver {payload.get('driver_name','on route')}.")
    if s.twilio_account_sid and s.twilio_auth_token:
        try:
            from twilio.rest import Client  # type: ignore
            sid = Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                body=msg, from_=s.twilio_from_number, to=consignee_phone).sid
            return {"sent": True, "sms_sid": sid, "to": consignee_phone, "eta": eta}
        except Exception as e:  # noqa: BLE001
            return {"sent": False, "error": str(e)}
    return {"sent": False, "note": "twilio_not_configured", "would_send": msg}


# ── Step 84: transit.dock_schedule ───────────────────────────────────────────

def h84_transit_dock_schedule(carrier_id, contract_id, payload):
    eta = payload.get("eta")
    dest = f"{payload.get('dest_city')},{payload.get('dest_state')}"
    sb = _db()
    dock_appointment = None
    if eta:
        try:
            eta_dt = datetime.fromisoformat(eta.replace("Z", "+00:00"))
            # Round to nearest half-hour for dock window
            mins = eta_dt.minute
            rounded = eta_dt.replace(minute=0 if mins < 30 else 30, second=0, microsecond=0)
            dock_appointment = rounded.isoformat()
        except Exception:  # noqa: BLE001
            pass
    if sb and payload.get("load_id"):
        try:
            sb.table("loads").update(
                {"dock_appointment": dock_appointment}
            ).eq("id", payload["load_id"]).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"scheduled": bool(dock_appointment), "dock_appointment": dock_appointment,
            "destination": dest, "load_id": payload.get("load_id")}


# ── Step 85: transit.hos_remaining ───────────────────────────────────────────

def h85_transit_hos_remaining(carrier_id, contract_id, payload):
    driver_code = payload.get("driver_code")
    miles_to_dest = float(payload.get("miles_remaining") or 0)
    avg_speed = 60.0
    hours_to_dest = miles_to_dest / avg_speed if avg_speed > 0 else 0
    sb = _db()
    drive_remaining = float(payload.get("drive_remaining_hrs") or 11.0)
    if sb and driver_code:
        try:
            r = sb.table("driver_hos_status").select("drive_remaining").eq(
                "driver_id", driver_code).maybe_single().execute()
            drive_remaining = float((r.data or {}).get("drive_remaining") or drive_remaining)
        except Exception:  # noqa: BLE001
            pass
    will_make_it = drive_remaining >= hours_to_dest
    return {"driver_code": driver_code, "drive_remaining_hrs": drive_remaining,
            "hours_to_dest": round(hours_to_dest, 2), "will_make_it": will_make_it,
            "rest_needed": not will_make_it}


# ── Step 86: transit.border_crossing ─────────────────────────────────────────

def h86_transit_border_crossing(carrier_id, contract_id, payload):
    crossing = payload.get("border_crossing", False)
    if not crossing:
        return {"applicable": False}
    ctpat = payload.get("ctpat_certified", False)
    paps = payload.get("paps_number")
    return {
        "applicable": True,
        "ctpat_certified": ctpat,
        "paps_number": paps,
        "docs_ready": bool(paps),
        "warnings": [] if (ctpat and paps) else ["CTPAT cert or PAPS missing"],
    }


# ── Step 87: transit.hazmat_compliance ───────────────────────────────────────

def h87_transit_hazmat_compliance(carrier_id, contract_id, payload):
    hazmat = payload.get("hazmat", False)
    if not hazmat:
        return {"applicable": False}
    placard = payload.get("placard_confirmed", False)
    manifest = payload.get("manifest_url")
    cleared = placard and bool(manifest)
    return {
        "applicable": True,
        "placard_confirmed": placard,
        "manifest_url": manifest,
        "cleared": cleared,
        "warnings": [] if cleared else ["Hazmat placard or manifest missing"],
    }


# ── Step 88: transit.temp_monitoring ─────────────────────────────────────────

def h88_transit_temp_monitoring(carrier_id, contract_id, payload):
    reefer = payload.get("trailer_type", "").lower() in ("reefer", "refrigerated")
    if not reefer:
        return {"applicable": False}
    current_temp = payload.get("current_temp_f")
    target_min = float(payload.get("target_temp_min", 34))
    target_max = float(payload.get("target_temp_max", 38))
    if current_temp is None:
        return {"applicable": True, "temp_recorded": False, "note": "no_temp_data"}
    in_range = target_min <= float(current_temp) <= target_max
    sb = _db()
    if sb and payload.get("load_id"):
        try:
            sb.table("loads").update({"last_temp_f": current_temp}).eq(
                "id", payload["load_id"]).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"applicable": True, "temp_recorded": True, "current_temp_f": current_temp,
            "target_range": [target_min, target_max], "in_range": in_range,
            "alert": not in_range}


# ── Step 89: transit.cargo_claim_detect ──────────────────────────────────────

def h89_transit_cargo_claim_detect(carrier_id, contract_id, payload):
    damage_reported = payload.get("damage_reported", False)
    damage_description = payload.get("damage_description")
    if not damage_reported:
        return {"risk_detected": False}
    sb = _db()
    if sb and payload.get("load_id"):
        try:
            sb.table("loads").update({
                "damage_reported": True,
                "damage_description": damage_description,
                "damage_reported_at": _NOW(),
            }).eq("id", payload["load_id"]).execute()
        except Exception:  # noqa: BLE001
            pass
    return {"risk_detected": True, "damage_description": damage_description,
            "load_id": payload.get("load_id"), "detected_at": _NOW(),
            "action": "flag_for_commander_review"}


# ── Step 90: transit.complete ─────────────────────────────────────────────────

def h90_transit_complete(carrier_id, contract_id, payload):
    load_id = payload.get("load_id")
    sb = _db()
    if sb and load_id:
        try:
            sb.table("loads").update({
                "status": "delivered",
                "delivered_at": _NOW(),
            }).eq("id", load_id).execute()
        except Exception:  # noqa: BLE001
            pass
    if sb and contract_id:
        try:
            sb.table("contracts").update({"milestone_pct": 90}).eq(
                "id", str(contract_id)).execute()
        except Exception:  # noqa: BLE001
            pass
    try:
        from ...atomic_ledger.service import write_event
        from ...atomic_ledger.models import AtomicEvent
        write_event(AtomicEvent(
            event_type="transit.complete",
            event_source="execution_engine.step_90",
            logistics_payload={"load_id": load_id, "truck_id": payload.get("truck_id"),
                               "driver_code": payload.get("driver_code"),
                               "delivered_at": _NOW()},
            financial_payload={"rate_total": payload.get("rate_total"),
                               "fuel_cost": payload.get("fuel_amount"),
                               "detention": payload.get("accrued", 0)},
            compliance_payload={"carrier_id": str(carrier_id) if carrier_id else None,
                                "milestone_pct": 90},
        ))
    except Exception as e:  # noqa: BLE001
        log.warning("atomic_ledger write failed at step 90: %s", e)
    return {"transit_complete": True, "load_id": load_id,
            "milestone_pct": 90, "completed_at": _NOW()}


TRANSIT_HANDLERS: dict = {
    61: h61_transit_pickup_confirmed,
    62: h62_document_vault_upload_bol,
    63: h63_scout_extract_bol,
    64: h64_clm_link_bol_to_contract,
    65: h65_orbit_gps_ping_loop,
    66: h66_pulse_hos_monitor,
    67: h67_signal_hos_warning,
    68: h68_atlas_checkcall_1,
    69: h69_atlas_checkcall_2,
    70: h70_signal_delay_alert,
    71: h71_orbit_geofence_delivery,
    72: h72_atlas_checkcall_3,
    73: h73_transit_weather_check,
    74: h74_transit_traffic_check,
    75: h75_signal_breakdown_detect,
    76: h76_signal_emergency_escalate,
    77: h77_transit_detention_clock,
    78: h78_transit_detention_notify,
    79: h79_transit_lumper_approve,
    80: h80_penny_fuel_cost_track,
    81: h81_transit_mid_route_safety,
    82: h82_transit_broker_visibility,
    83: h83_transit_eta_sms_update,
    84: h84_transit_dock_schedule,
    85: h85_transit_hos_remaining,
    86: h86_transit_border_crossing,
    87: h87_transit_hazmat_compliance,
    88: h88_transit_temp_monitoring,
    89: h89_transit_cargo_claim_detect,
    90: h90_transit_complete,
}

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
}

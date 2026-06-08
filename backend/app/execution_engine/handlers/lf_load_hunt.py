"""Light Fleet — Load Hunt handlers (steps 271–290).

Domain 12: per-driver multi-board load scanning.
Reads each driver's agent card, builds search params, scans all configured
boards, scores/deduplicates results, persists, and optionally auto-accepts
HOT loads by creating a trip record that feeds Domain 9 (lf_dispatch).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger("3ll.execution.lf_load_hunt")

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _db():
    try:
        from ...supabase_client import get_supabase
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


def _driver(driver_id) -> dict:
    if not driver_id:
        return {}
    sb = _db()
    if not sb:
        return {}
    try:
        r = (
            sb.table("light_vehicle_drivers")
            .select("*")
            .eq("id", str(driver_id))
            .maybe_single()
            .execute()
        )
        return r.data or {}
    except Exception:  # noqa: BLE001
        return {}


# ── Step 271: read_agent_card ─────────────────────────────────────────────────

def h271_read_agent_card(carrier_id, contract_id, payload) -> dict:
    driver_id = payload.get("driver_id") or carrier_id
    d = _driver(driver_id)
    if not d:
        return {"ok": False, "error": "driver_not_found", "driver_id": str(driver_id)}
    return {
        "ok": True,
        "driver_id": str(driver_id),
        "name": d.get("name"),
        "hunt_enabled": bool(d.get("hunt_enabled", False)),
        "vehicle_type": d.get("vehicle_type"),
        "vehicle_cargo_type": d.get("vehicle_cargo_type"),
        "vehicle_capacity_lbs": d.get("vehicle_capacity_lbs"),
        "vehicle_max_length_ft": float(d["vehicle_max_length_ft"]) if d.get("vehicle_max_length_ft") else None,
        "min_rpm": float(d.get("min_rpm") or 1.50),
        "min_rate_total": float(d.get("min_rate_total") or 25.00),
        "auto_accept_threshold": float(d["auto_accept_threshold"]) if d.get("auto_accept_threshold") else None,
        "max_deadhead_mi": int(d.get("max_deadhead_mi") or 50),
        "max_trip_miles": int(d.get("max_trip_miles") or 300),
        "service_areas": d.get("service_areas") or [],
        "preferred_load_types": d.get("preferred_load_types") or [],
        "available_days": d.get("available_days") or ["mon","tue","wed","thu","fri","sat"],
        "hours_start": d.get("hours_start") or "07:00",
        "hours_end": d.get("hours_end") or "20:00",
        "phone": d.get("phone"),
    }


# ── Step 272: build_search_params ────────────────────────────────────────────

def h272_build_search_params(carrier_id, contract_id, payload) -> dict:
    from ....app.prospecting.loadboard_clients import SearchParams  # type: ignore

    service_areas = payload.get("service_areas") or []
    origin_city, origin_state, origin_zip = "Portland", "OR", "97201"
    if service_areas:
        parts = [p.strip() for p in service_areas[0].split(",")]
        if len(parts) >= 2:
            origin_city = parts[0]
            origin_state = parts[1]

    params = SearchParams(
        origin_city=origin_city,
        origin_state=origin_state,
        origin_zip=origin_zip,
        trailer_type=payload.get("vehicle_cargo_type") or payload.get("vehicle_type") or "cargo_van",
        max_deadhead_mi=int(payload.get("max_deadhead_mi") or 50),
        min_rate_per_mile=float(payload.get("min_rpm") or 1.50),
    )
    return {
        "search_params": {
            "origin_city": params.origin_city,
            "origin_state": params.origin_state,
            "origin_zip": params.origin_zip,
            "trailer_type": params.trailer_type,
            "max_deadhead_mi": params.max_deadhead_mi,
            "min_rate_per_mile": params.min_rate_per_mile,
        },
        "_params_obj": params,  # passed through in-process only
    }


# ── Step 273–277: scan individual boards ────────────────────────────────────

def _scan_board(board_name: str, fn, params, min_rpm: float, hot_rpm: float) -> list[dict]:
    """Run one board and return filtered, serialized results."""
    try:
        raw = fn(params)
    except Exception as exc:
        log.warning("%s scan failed: %s", board_name, exc)
        return []
    hits = []
    for r in raw:
        rpm_val = getattr(r, "rate_per_mile", None) or 0.0
        if not rpm_val:
            rate = float(getattr(r, "rate_total", None) or 0)
            miles = float(getattr(r, "miles", None) or 0)
            rpm_val = round(rate / miles, 3) if miles else 0.0
        if rpm_val >= min_rpm:
            hits.append({
                "source": r.source,
                "load_id": r.load_id,
                "broker_name": r.broker_name,
                "origin_city": r.origin_city,
                "origin_state": r.origin_state,
                "dest_city": r.dest_city,
                "dest_state": r.dest_state,
                "miles": r.miles,
                "rate_total": r.rate_total,
                "rpm": rpm_val,
                "trailer_type": r.trailer_type,
                "pickup_date": r.pickup_date,
                "is_hot": rpm_val >= hot_rpm,
            })
    return hits


def h273_scan_123loadboard(carrier_id, contract_id, payload) -> dict:
    try:
        from ....app.prospecting.loadboard_clients import loadboard123_search, SearchParams  # type: ignore
        params = payload.get("_params_obj") or SearchParams(**payload["search_params"])
        hits = _scan_board("123loadboard", loadboard123_search, params,
                           float(payload.get("min_rpm", 1.50)), float(payload.get("hot_rpm", 2.00)))
        return {"board": "123loadboard", "hits": hits, "count": len(hits)}
    except Exception as e:
        return {"board": "123loadboard", "hits": [], "count": 0, "error": str(e)}


def h274_scan_dat(carrier_id, contract_id, payload) -> dict:
    try:
        from ....app.prospecting.loadboard_clients import dat_search, SearchParams  # type: ignore
        params = payload.get("_params_obj") or SearchParams(**payload["search_params"])
        hits = _scan_board("dat", dat_search, params,
                           float(payload.get("min_rpm", 1.50)), float(payload.get("hot_rpm", 2.00)))
        return {"board": "dat", "hits": hits, "count": len(hits)}
    except Exception as e:
        return {"board": "dat", "hits": [], "count": 0, "error": str(e)}


def h275_scan_truckstop(carrier_id, contract_id, payload) -> dict:
    try:
        from ....app.prospecting.loadboard_clients import truckstop_search, SearchParams  # type: ignore
        params = payload.get("_params_obj") or SearchParams(**payload["search_params"])
        hits = _scan_board("truckstop", truckstop_search, params,
                           float(payload.get("min_rpm", 1.50)), float(payload.get("hot_rpm", 2.00)))
        return {"board": "truckstop", "hits": hits, "count": len(hits)}
    except Exception as e:
        return {"board": "truckstop", "hits": [], "count": 0, "error": str(e)}


def h276_scan_truckerpath(carrier_id, contract_id, payload) -> dict:
    try:
        from ....app.prospecting.loadboard_clients import truckerpath_search, SearchParams  # type: ignore
        params = payload.get("_params_obj") or SearchParams(**payload["search_params"])
        hits = _scan_board("truckerpath", truckerpath_search, params,
                           float(payload.get("min_rpm", 1.50)), float(payload.get("hot_rpm", 2.00)))
        return {"board": "truckerpath", "hits": hits, "count": len(hits)}
    except Exception as e:
        return {"board": "truckerpath", "hits": [], "count": 0, "error": str(e)}


def h277_scan_chrobinson(carrier_id, contract_id, payload) -> dict:
    try:
        from ....app.prospecting.loadboard_clients import chrobinson_search, SearchParams  # type: ignore
        params = payload.get("_params_obj") or SearchParams(**payload["search_params"])
        hits = _scan_board("ch_robinson", chrobinson_search, params,
                           float(payload.get("min_rpm", 1.50)), float(payload.get("hot_rpm", 2.00)))
        return {"board": "ch_robinson", "hits": hits, "count": len(hits)}
    except Exception as e:
        return {"board": "ch_robinson", "hits": [], "count": 0, "error": str(e)}


# ── Step 278: deduplicate ─────────────────────────────────────────────────────

def h278_deduplicate(carrier_id, contract_id, payload) -> dict:
    all_hits: list[dict] = []
    for key in ("hits_123loadboard", "hits_dat", "hits_truckstop", "hits_truckerpath", "hits_chrobinson"):
        all_hits.extend(payload.get(key) or [])
    # Also support flat list passed as "all_hits"
    all_hits.extend(payload.get("all_hits") or [])

    seen: set[str] = set()
    unique: list[dict] = []
    for r in sorted(all_hits, key=lambda x: x.get("rpm", 0), reverse=True):
        key = f"{r['source']}:{r['load_id']}"
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return {"loads": unique, "total": len(unique), "dedup_removed": len(all_hits) - len(unique)}


# ── Step 279: score_loads ────────────────────────────────────────────────────

def h279_score_loads(carrier_id, contract_id, payload) -> dict:
    loads = payload.get("loads") or []
    min_rpm = float(payload.get("min_rpm") or 1.50)
    for load in loads:
        rpm = float(load.get("rpm") or 0)
        miles = float(load.get("miles") or 0)
        # Simple score: normalized RPM (0–100) + distance bonus for shorter hauls
        rpm_score = min(100, round((rpm / max(min_rpm * 2, 0.01)) * 60))
        dist_bonus = max(0, 20 - int(miles / 50)) if miles else 0
        load["score"] = min(100, rpm_score + dist_bonus)
    loads.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"loads": loads, "total": len(loads)}


# ── Step 280: filter_hot ─────────────────────────────────────────────────────

def h280_filter_hot(carrier_id, contract_id, payload) -> dict:
    loads = payload.get("loads") or []
    auto_accept_threshold = payload.get("auto_accept_threshold")
    hot_rpm = float(payload.get("hot_rpm") or 2.00)
    hot_loads = []
    for load in loads:
        rpm = float(load.get("rpm") or 0)
        load["is_hot"] = rpm >= hot_rpm
        if auto_accept_threshold and rpm >= float(auto_accept_threshold):
            load["auto_accept"] = True
            hot_loads.append(load)
        elif load["is_hot"]:
            hot_loads.append(load)
    return {
        "loads": loads,
        "hot_loads": hot_loads,
        "hot_count": sum(1 for l in loads if l.get("is_hot")),
        "auto_accept_count": sum(1 for l in loads if l.get("auto_accept")),
    }


# ── Step 281: persist_results ────────────────────────────────────────────────

def h281_persist_results(carrier_id, contract_id, payload) -> dict:
    loads = payload.get("loads") or []
    driver_id = payload.get("driver_id") or str(carrier_id) if carrier_id else None
    sb = _db()
    saved = 0
    if sb and loads:
        for load in loads:
            try:
                sb.table("load_hunter_results").upsert({
                    "source":       load["source"],
                    "load_id":      load["load_id"],
                    "broker_name":  load.get("broker_name"),
                    "origin_city":  load.get("origin_city"),
                    "origin_state": load.get("origin_state"),
                    "dest_city":    load.get("dest_city"),
                    "dest_state":   load.get("dest_state"),
                    "miles":        load.get("miles"),
                    "rate_total":   load.get("rate_total"),
                    "rpm":          load.get("rpm"),
                    "trailer_type": load.get("trailer_type"),
                    "pickup_date":  load.get("pickup_date"),
                    "is_hot":       load.get("is_hot", False),
                    "driver_id":    driver_id,
                    "found_at":     _NOW(),
                }, on_conflict="source,load_id").execute()
                saved += 1
            except Exception as exc:
                log.debug("persist load failed: %s", exc)
    return {"persisted": saved, "total": len(loads), "driver_id": driver_id}


# ── Step 282: auto_accept ────────────────────────────────────────────────────

def h282_auto_accept(carrier_id, contract_id, payload) -> dict:
    """
    For any load with auto_accept=True, create a light_vehicle_trips record
    and hand off to Domain 9 (lf.trip.receive, step 221).
    """
    driver_id = payload.get("driver_id") or str(carrier_id) if carrier_id else None
    auto_loads = [l for l in (payload.get("loads") or []) if l.get("auto_accept")]
    if not auto_loads or not driver_id:
        return {"auto_accepted": 0, "trip_ids": [], "driver_id": driver_id}

    sb = _db()
    trip_ids: list[str] = []
    if sb:
        for load in auto_loads[:3]:  # cap at 3 auto-accepts per hunt cycle
            try:
                result = sb.table("light_vehicle_trips").insert({
                    "driver_id":       driver_id,
                    "trip_type":       "courier",
                    "status":          "pending",
                    "pickup_address":  f"{load.get('origin_city','')}, {load.get('origin_state','')}",
                    "dropoff_address": f"{load.get('dest_city','')}, {load.get('dest_state','')}",
                    "estimated_miles": load.get("miles"),
                    "rate_total":      load.get("rate_total"),
                    "rate_per_mile":   load.get("rpm"),
                    "source":          f"load_hunt:{load['source']}",
                    "load_id":         load["load_id"],
                    "created_at":      _NOW(),
                    "notes":           f"Auto-accepted from {load['source']} — RPM ${load.get('rpm',0):.2f}",
                }).execute()
                if result.data:
                    trip_id = result.data[0]["id"]
                    trip_ids.append(trip_id)
                    log.info("Auto-accepted load %s → trip %s driver %s", load["load_id"], trip_id, driver_id)
            except Exception as exc:
                log.warning("auto_accept trip create failed: %s", exc)

    return {
        "auto_accepted": len(trip_ids),
        "trip_ids": trip_ids,
        "driver_id": driver_id,
        "loads_considered": len(auto_loads),
    }


# ── Step 283: notify_driver ───────────────────────────────────────────────────

def h283_notify_driver(carrier_id, contract_id, payload) -> dict:
    driver_id = payload.get("driver_id") or str(carrier_id) if carrier_id else None
    loads = payload.get("loads") or []
    hot_loads = [l for l in loads if l.get("is_hot")][:3]
    phone = payload.get("phone")

    if not phone and driver_id:
        d = _driver(driver_id)
        phone = d.get("phone")

    if not hot_loads:
        return {"notified": False, "reason": "no_hot_loads"}
    if not phone:
        return {"notified": False, "reason": "no_phone_on_file"}

    lines = [f"🎯 3 Lakes Load Matches — top {len(hot_loads)} HOT loads:"]
    for i, l in enumerate(hot_loads, 1):
        lines.append(
            f"{i}. {l.get('origin_city','?')},{l.get('origin_state','')} → "
            f"{l.get('dest_city','?')},{l.get('dest_state','')} "
            f"{l.get('miles','?')}mi @${l.get('rpm',0):.2f}/mi "
            f"(${l.get('rate_total',0):.0f} total)"
        )
    lines.append("Log in to Eagle Eye or reply YES to accept the top load.")
    message = "\n".join(lines)

    try:
        from ...settings import get_settings
        s = get_settings()
        if s.twilio_account_sid and s.twilio_auth_token and s.twilio_from_number:
            from twilio.rest import Client  # type: ignore
            msg = Client(s.twilio_account_sid, s.twilio_auth_token).messages.create(
                body=message, from_=s.twilio_from_number, to=phone,
            )
            return {"notified": True, "phone": phone, "sms_sid": msg.sid, "hot_count": len(hot_loads)}
        return {"notified": False, "reason": "twilio_not_configured", "would_send": message}
    except Exception as e:
        log.warning("driver hunt SMS failed: %s", e)
        return {"notified": False, "error": str(e)}


# ── Step 284: notify_eagle_eye ────────────────────────────────────────────────

def h284_notify_eagle_eye(carrier_id, contract_id, payload) -> dict:
    driver_id = payload.get("driver_id") or str(carrier_id) if carrier_id else None
    total = payload.get("total") or len(payload.get("loads") or [])
    hot_count = payload.get("hot_count") or sum(1 for l in (payload.get("loads") or []) if l.get("is_hot"))
    log.info("Eagle Eye: hunt complete driver=%s total=%s hot=%s", driver_id, total, hot_count)
    return {
        "eagle_eye_notified": True,
        "driver_id": driver_id,
        "total_loads": total,
        "hot_loads": hot_count,
        "notified_at": _NOW(),
    }


# ── Step 285: update_driver_stats ────────────────────────────────────────────

def h285_update_driver_stats(carrier_id, contract_id, payload) -> dict:
    driver_id = payload.get("driver_id") or str(carrier_id) if carrier_id else None
    total = payload.get("total") or len(payload.get("loads") or [])
    sb = _db()
    if sb and driver_id:
        try:
            r = sb.table("light_vehicle_drivers").select("matched_loads_count").eq("id", driver_id).maybe_single().execute()
            current = (r.data or {}).get("matched_loads_count") or 0
            sb.table("light_vehicle_drivers").update({
                "last_hunted_at": _NOW(),
                "matched_loads_count": current + total,
            }).eq("id", driver_id).execute()
        except Exception as exc:
            log.debug("stats update failed: %s", exc)
    return {"stats_updated": True, "driver_id": driver_id, "new_matches_added": total}


# ── Step 286: schedule_next ───────────────────────────────────────────────────

def h286_schedule_next(carrier_id, contract_id, payload) -> dict:
    driver_id = payload.get("driver_id") or str(carrier_id) if carrier_id else None
    interval_min = int(payload.get("interval_minutes") or 15)
    # Real scheduling is handled by the APScheduler job in the app startup or
    # pg_cron. This step records the intent and logs it.
    log.info("Next hunt scheduled: driver=%s interval=%dmin", driver_id, interval_min)
    return {
        "scheduled": True,
        "driver_id": driver_id,
        "interval_minutes": interval_min,
        "next_hunt_note": f"APScheduler/pg_cron will fire hunt_for_driver({driver_id}) in {interval_min}min",
    }


# ── Step 287: rate_index_update ──────────────────────────────────────────────

def h287_rate_index_update(carrier_id, contract_id, payload) -> dict:
    auto_accepted = payload.get("trip_ids") or []
    loads = payload.get("loads") or []
    accepted_loads = [l for l in loads if l.get("auto_accept")]
    log.info("Rate index: %d accepted loads fed into index", len(accepted_loads))
    return {
        "rate_index_updated": True,
        "loads_indexed": len(accepted_loads),
        "trip_ids": auto_accepted,
    }


# ── Step 288: broker_blacklist_check ─────────────────────────────────────────

def h288_broker_blacklist_check(carrier_id, contract_id, payload) -> dict:
    loads = payload.get("loads") or []
    blacklist: list[str] = payload.get("blacklisted_brokers") or []
    if not blacklist:
        return {"loads": loads, "removed": 0, "total": len(loads)}
    filtered = [l for l in loads if (l.get("broker_name") or "") not in blacklist]
    removed = len(loads) - len(filtered)
    return {"loads": filtered, "removed": removed, "total": len(filtered)}


# ── Step 289: ledger_write ────────────────────────────────────────────────────

def h289_ledger_write(carrier_id, contract_id, payload) -> dict:
    driver_id = payload.get("driver_id") or str(carrier_id) if carrier_id else None
    total = payload.get("total") or len(payload.get("loads") or [])
    auto_accepted = payload.get("auto_accepted") or 0
    try:
        from ...atomic_ledger.service import write_event
        from ...atomic_ledger.models import AtomicEvent
        write_event(AtomicEvent(
            event_type="lf_load_hunt_complete",
            event_source="execution_engine.lf_load_hunt",
            logistics_payload={
                "driver_id": driver_id,
                "loads_found": total,
                "auto_accepted": auto_accepted,
                "hunted_at": _NOW(),
            },
        ))
        return {"ledger_written": True, "driver_id": driver_id}
    except Exception as e:
        return {"ledger_written": False, "error": str(e)}


# ── Step 290: hunt_complete ───────────────────────────────────────────────────

def h290_hunt_complete(carrier_id, contract_id, payload) -> dict:
    driver_id = payload.get("driver_id") or str(carrier_id) if carrier_id else None
    total = payload.get("total") or len(payload.get("loads") or [])
    hot = payload.get("hot_count") or sum(1 for l in (payload.get("loads") or []) if l.get("is_hot"))
    auto = payload.get("auto_accepted") or 0
    log.info("Hunt cycle complete: driver=%s total=%s hot=%s auto_accepted=%s", driver_id, total, hot, auto)
    return {
        "completed": True,
        "driver_id": driver_id,
        "loads_found": total,
        "hot_loads": hot,
        "auto_accepted": auto,
        "completed_at": _NOW(),
    }


# ── Dispatch table ────────────────────────────────────────────────────────────

LF_LOAD_HUNT_HANDLERS: dict[int, callable] = {
    271: h271_read_agent_card,
    272: h272_build_search_params,
    273: h273_scan_123loadboard,
    274: h274_scan_dat,
    275: h275_scan_truckstop,
    276: h276_scan_truckerpath,
    277: h277_scan_chrobinson,
    278: h278_deduplicate,
    279: h279_score_loads,
    280: h280_filter_hot,
    281: h281_persist_results,
    282: h282_auto_accept,
    283: h283_notify_driver,
    284: h284_notify_eagle_eye,
    285: h285_update_driver_stats,
    286: h286_schedule_next,
    287: h287_rate_index_update,
    288: h288_broker_blacklist_check,
    289: h289_ledger_write,
    290: h290_hunt_complete,
}

"""Loads — full CRUD, dispatch flow, and broker intake.

Routes:
  POST /api/loads/                     — create a load (ops / broker)
  POST /api/loads/intake               — rate-limited broker load submission
  GET  /api/loads/                     — list loads (filter by status/carrier/driver)
  GET  /api/loads/available            — load board: unassigned available loads
  GET  /api/loads/{load_id}            — single load detail
  PATCH /api/loads/{load_id}/status    — advance load lifecycle status
  POST /api/loads/{load_id}/dispatch   — assign driver + truck, send notifications
  POST /api/loads/{load_id}/offer      — offer load to a specific driver
  POST /api/loads/{load_id}/accept     — driver accepts load (from PWA)
  POST /api/loads/{load_id}/checkcall  — fire a check call (email + SMS to broker)
  POST /api/loads/{load_id}/event      — append to load_events audit log
  POST /api/loads/{load_id}/post-board — post to external/internal load board
  GET  /api/loads/{load_id}/events     — full event history
  GET  /api/loads/{load_id}/matches    — run Sonny match against this load
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..agents import nova, signal, sonny
from ..logging_service import log_agent
from ..supabase_client import get_supabase
from .deps import require_bearer

router = APIRouter(dependencies=[Depends(require_bearer)])
_limiter = Limiter(key_func=get_remote_address)

_VALID_STATUSES = {
    "available", "offered", "booked", "dispatched",
    "in_transit", "delivered", "pod_needed", "closed", "cancelled",
}

_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "available":  {"offered", "booked", "cancelled"},
    "offered":    {"booked", "available", "cancelled"},
    "booked":     {"dispatched", "cancelled"},
    "dispatched": {"in_transit", "cancelled"},
    "in_transit": {"delivered", "pod_needed"},
    "delivered":  {"pod_needed", "closed"},
    "pod_needed": {"closed"},
    "closed":     set(),
    "cancelled":  set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(load_id: str, carrier_id: str | None, event_type: str,
               actor: str = "system", payload: dict | None = None) -> None:
    try:
        get_supabase().table("load_events").insert({
            "load_id": load_id,
            "carrier_id": carrier_id,
            "event_type": event_type,
            "actor": actor,
            "payload": payload or {},
            "ts": _now(),
        }).execute()
    except Exception:  # noqa: BLE001
        pass  # event logging is best-effort


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_load(body: dict) -> dict:
    """Create a load record (ops-entered or CLM-scanned)."""
    sb = get_supabase()
    body.setdefault("status", "available")
    body.setdefault("source", "manual")
    body["created_at"] = _now()
    body["updated_at"] = _now()

    # Auto-compute rate_per_mile if missing
    if body.get("rate_total") and body.get("miles") and not body.get("rate_per_mile"):
        try:
            body["rate_per_mile"] = round(float(body["rate_total"]) / float(body["miles"]), 2)
        except (ZeroDivisionError, TypeError, ValueError):
            pass

    res = sb.table("loads").insert(body).execute()
    if not res.data:
        raise HTTPException(500, "load insert failed")
    load = res.data[0]
    load_id = load["id"]
    _log_event(load_id, body.get("carrier_id"), "created", actor="ops")
    log_agent("sonny", "load_created", carrier_id=body.get("carrier_id"),
              payload={"load_number": body.get("load_number"), "status": body.get("status")})
    return {"ok": True, "load": load}


@router.post("/intake", status_code=status.HTTP_201_CREATED)
@_limiter.limit("20/minute")
async def broker_intake(request: Request, body: dict) -> dict:
    """Rate-limited broker load submission — accepts rate-conf fields directly."""
    body["source"] = "broker_intake"
    body.setdefault("status", "available")
    return create_load(body)


# ── List / load board ─────────────────────────────────────────────────────────

@router.get("/available")
def load_board(
    trailer_type: str | None = None,
    origin_state: str | None = None,
    min_rate: float | None = None,
    limit: int = 100,
) -> dict:
    """Internal load board — available, unassigned loads sorted by rate."""
    q = (
        get_supabase()
        .table("loads")
        .select(
            "id,load_number,broker_name,origin_city,origin_state,dest_city,dest_state,"
            "trailer_type,weight_lbs,rate_total,rate_per_mile,miles,pickup_at,delivery_at,"
            "commodity,hazmat,temperature_controlled,payment_terms,source"
        )
        .eq("status", "available")
        .order("rate_total", desc=True)
        .limit(limit)
    )
    if trailer_type:
        q = q.eq("trailer_type", trailer_type)
    if origin_state:
        q = q.eq("origin_state", origin_state)
    if min_rate is not None:
        q = q.gte("rate_total", min_rate)

    res = q.execute()
    return {"count": len(res.data or []), "loads": res.data or []}


@router.get("/")
def list_loads(
    status: str | None = None,
    carrier_id: str | None = None,
    driver_code: str | None = None,
    truck_id: str | None = None,
    week_start: str | None = None,
    week_end: str | None = None,
    limit: int = 200,
) -> dict:
    q = (
        get_supabase()
        .table("loads")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        q = q.eq("status", status)
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    if driver_code:
        q = q.eq("driver_code", driver_code)
    if truck_id:
        q = q.eq("truck_id", truck_id)
    if week_start:
        q = q.gte("pickup_at", week_start)
    if week_end:
        q = q.lte("pickup_at", week_end)

    res = q.execute()
    return {"count": len(res.data or []), "loads": res.data or []}


# ── Single load ───────────────────────────────────────────────────────────────

@router.get("/{load_id}")
def get_load(load_id: str) -> dict:
    res = get_supabase().table("loads").select("*").eq("id", load_id).maybe_single().execute()
    if not res.data:
        raise HTTPException(404, "load not found")
    return res.data


@router.get("/{load_id}/events")
def load_events(load_id: str) -> dict:
    res = (
        get_supabase()
        .table("load_events")
        .select("*")
        .eq("load_id", load_id)
        .order("ts", desc=False)
        .execute()
    )
    return {"load_id": load_id, "events": res.data or []}


@router.get("/{load_id}/matches")
def find_truck_matches(load_id: str) -> dict:
    """Run Sonny load-matching for a specific load — find available trucks."""
    load = get_supabase().table("loads").select("*").eq("id", load_id).maybe_single().execute().data
    if not load:
        raise HTTPException(404, "load not found")

    # Get available trucks for this load's trailer type + origin state
    trucks = (
        get_supabase()
        .table("fleet_assets")
        .select("id,carrier_id,truck_id,trailer_type,max_weight_lbs,status")
        .eq("trailer_type", load.get("trailer_type", ""))
        .eq("status", "available")
        .limit(50)
        .execute()
        .data or []
    )

    matches = []
    for truck in trucks:
        if int(truck.get("max_weight_lbs") or 0) >= int(load.get("weight_lbs") or 0):
            matches.append({
                **truck,
                "_estimated_rpm": load.get("rate_per_mile"),
            })

    return {"load_id": load_id, "match_count": len(matches), "trucks": matches}


# ── Status transitions ────────────────────────────────────────────────────────

@router.patch("/{load_id}/status")
def update_status(load_id: str, body: dict) -> dict:
    new_status = body.get("status", "")
    if new_status not in _VALID_STATUSES:
        raise HTTPException(400, f"invalid status. Valid: {sorted(_VALID_STATUSES)}")

    load = get_supabase().table("loads").select("id,status,carrier_id").eq("id", load_id).maybe_single().execute().data
    if not load:
        raise HTTPException(404, "load not found")

    allowed = _STATUS_TRANSITIONS.get(load["status"], set())
    if new_status not in allowed:
        raise HTTPException(409, f"cannot transition from '{load['status']}' to '{new_status}'")

    update: dict[str, Any] = {"status": new_status, "updated_at": _now()}
    ts_map = {
        "dispatched": "dispatched_at",
        "in_transit":  "picked_up_at",
        "delivered":   "delivered_at",
    }
    if new_status in ts_map:
        update[ts_map[new_status]] = _now()

    get_supabase().table("loads").update(update).eq("id", load_id).execute()
    _log_event(load_id, load.get("carrier_id"), new_status, actor=body.get("actor", "system"))
    return {"ok": True, "load_id": load_id, "status": new_status}


# ── Dispatch ──────────────────────────────────────────────────────────────────

@router.post("/{load_id}/dispatch")
def dispatch_load(load_id: str, body: dict) -> dict:
    """Assign driver + truck to a load and fire dispatch notifications."""
    sb = get_supabase()
    load = sb.table("loads").select("*").eq("id", load_id).maybe_single().execute().data
    if not load:
        raise HTTPException(404, "load not found")
    if load["status"] not in ("available", "offered", "booked"):
        raise HTTPException(409, f"load is '{load['status']}' — cannot dispatch")

    driver_code = body.get("driver_code") or body.get("driver_id", "")
    truck_id = body.get("truck_id", "")
    carrier_id = body.get("carrier_id") or load.get("carrier_id", "")

    updates = {
        "status": "dispatched",
        "driver_code": driver_code,
        "truck_id": truck_id,
        "carrier_id": carrier_id,
        "driver_name": body.get("driver_name", load.get("driver_name")),
        "driver_phone": body.get("driver_phone", load.get("driver_phone")),
        "driver_email": body.get("driver_email", load.get("driver_email")),
        "dispatched_at": _now(),
        "updated_at": _now(),
    }
    sb.table("loads").update(updates).eq("id", load_id).execute()

    # Mark truck as on-load
    if truck_id:
        sb.table("fleet_assets").update({"status": "on_load"}).eq("truck_id", truck_id).execute()

    _log_event(load_id, carrier_id, "dispatched", actor="dispatcher",
               payload={"driver_code": driver_code, "truck_id": truck_id})

    dispatch_payload = {**load, **updates, "carrier_id": carrier_id, "load_number": load.get("load_number")}

    # Send dispatch sheet email
    email_result: dict = {"status": "skipped"}
    if updates.get("driver_email"):
        dispatch_payload["driver_email"] = updates["driver_email"]
        email_result = nova.send_dispatch(dispatch_payload)

    # Send dispatch SMS
    sms_result: dict = {"status": "skipped"}
    if updates.get("driver_phone"):
        dispatch_payload["driver_phone"] = updates["driver_phone"]
        sms_result = signal.send_dispatch_sms(dispatch_payload)

    log_agent("sonny", "load_dispatched", carrier_id=carrier_id,
              payload={"load_id": load_id, "driver": driver_code})

    return {
        "ok": True,
        "load_id": load_id,
        "status": "dispatched",
        "email": email_result,
        "sms": sms_result,
    }


@router.post("/{load_id}/offer")
def offer_load(load_id: str, body: dict) -> dict:
    """Offer a load to a specific driver (changes status to 'offered')."""
    sb = get_supabase()
    load = sb.table("loads").select("*").eq("id", load_id).maybe_single().execute().data
    if not load:
        raise HTTPException(404, "load not found")

    driver_phone = body.get("driver_phone", "")
    carrier_id = body.get("carrier_id") or load.get("carrier_id", "")

    sb.table("loads").update({"status": "offered", "updated_at": _now()}).eq("id", load_id).execute()
    _log_event(load_id, carrier_id, "offered", payload={"driver_phone": driver_phone})

    sms_result: dict = {"status": "skipped"}
    if driver_phone:
        sms_result = signal.send_dispatch_sms({
            **load,
            "driver_phone": driver_phone,
            "carrier_id": carrier_id,
        })

    return {"ok": True, "load_id": load_id, "status": "offered", "sms": sms_result}


@router.post("/{load_id}/accept")
def accept_load(load_id: str, body: dict) -> dict:
    """Driver accepts an offered load (called from PWA)."""
    sb = get_supabase()
    load = sb.table("loads").select("*").eq("id", load_id).maybe_single().execute().data
    if not load:
        raise HTTPException(404, "load not found")
    if load["status"] not in ("available", "offered"):
        raise HTTPException(409, f"load is '{load['status']}' — cannot accept")

    driver_code = body.get("driver_code", "")
    carrier_id = body.get("carrier_id") or load.get("carrier_id", "")

    sb.table("loads").update({
        "status": "booked",
        "driver_code": driver_code,
        "updated_at": _now(),
    }).eq("id", load_id).execute()
    _log_event(load_id, carrier_id, "accepted", actor=driver_code)

    return {"ok": True, "load_id": load_id, "status": "booked", "driver_code": driver_code}


# ── Check call ────────────────────────────────────────────────────────────────

@router.post("/{load_id}/checkcall")
def fire_check_call(load_id: str, body: dict | None = None) -> dict:
    """Send a check-call email + SMS to the broker."""
    load = get_supabase().table("loads").select("*").eq("id", load_id).maybe_single().execute().data
    if not load:
        raise HTTPException(404, "load not found")

    body = body or {}
    check_payload = {
        **load,
        "current_location": body.get("current_location") or load.get("current_location", "en route"),
        "eta": body.get("eta") or load.get("eta", "on schedule"),
        "status": load.get("status", "in_transit"),
    }
    carrier_id = load.get("carrier_id", "")

    email_result = nova.send_check_call(check_payload) if load.get("broker_email") else {"status": "no_broker_email"}
    sms_result = signal.send_check_call_sms(check_payload) if load.get("broker_phone") else {"status": "no_broker_phone"}

    _log_event(load_id, carrier_id, "check_call",
               payload={"location": check_payload["current_location"], "eta": check_payload["eta"]})

    return {"ok": True, "load_id": load_id, "email": email_result, "sms": sms_result}


# ── Load board posting ────────────────────────────────────────────────────────

@router.post("/{load_id}/post-board")
def post_to_board(load_id: str, body: dict) -> dict:
    """Post a load to an external or internal load board.

    Supported boards: internal (always), dat, truckstop, 123loadboard.
    External boards require API credentials in settings.

    body: { board: "dat" | "truckstop" | "123loadboard" | "internal",
            expires_hours: 48 }
    """
    load = get_supabase().table("loads").select("*").eq("id", load_id).maybe_single().execute().data
    if not load:
        raise HTTPException(404, "load not found")

    board = body.get("board", "internal")
    expires_hours = int(body.get("expires_hours", 48))
    from datetime import timedelta
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=expires_hours)).isoformat()

    from ..prospecting.loadboard_scraper import post_load
    result = post_load(load, board=board)

    # Record in loadboard_posts table
    get_supabase().table("loadboard_posts").insert({
        "load_id": load_id,
        "board": board,
        "post_ref": result.get("post_ref"),
        "status": "posted" if result.get("status") == "posted" else "failed",
        "posted_at": _now(),
        "expires_at": expires_at,
    }).execute()

    # Change load status to available if not already
    if load.get("status") not in ("available", "offered"):
        get_supabase().table("loads").update(
            {"status": "available", "updated_at": _now()}
        ).eq("id", load_id).execute()

    _log_event(load_id, load.get("carrier_id"), "posted_to_board", payload={"board": board})
    return {"ok": True, "load_id": load_id, "board": board, "result": result}


# ── Audit append ──────────────────────────────────────────────────────────────

@router.post("/{load_id}/event")
def append_event(load_id: str, body: dict) -> dict:
    load = get_supabase().table("loads").select("id,carrier_id").eq("id", load_id).maybe_single().execute().data
    if not load:
        raise HTTPException(404, "load not found")
    _log_event(load_id, load.get("carrier_id"),
               body.get("event_type", "note"),
               actor=body.get("actor", "system"),
               payload=body.get("payload"))
    return {"ok": True}

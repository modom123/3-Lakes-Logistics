"""Telemetry + HOS — powers the EAGLE EYE live map and HOS widgets."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..logging_service import get_logger
from ..models.telemetry import HosStatus, NativePing, TelemetryPing
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("route.telemetry")

router = APIRouter(dependencies=[Depends(require_bearer)])


@router.post("/ping")
def ingest_ping(ping: TelemetryPing) -> dict:
    try:
        get_supabase().table("truck_telemetry").insert(ping.model_dump(exclude_none=True)).execute()
    except Exception as e:
        log.error("truck_telemetry insert failed: %s", e)
        raise HTTPException(500, f"telemetry insert failed: {e}")
    return {"ok": True}


@router.get("/latest")
def latest_positions(carrier_id: str | None = None, limit: int = 200) -> dict:
    q = (
        get_supabase()
        .table("truck_telemetry")
        .select("carrier_id,truck_id,lat,lng,speed_mph,heading,ts")
        .order("ts", desc=True)
        .limit(limit)
    )
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    res = q.execute()
    # dedupe keeping first-seen (latest) per truck
    seen: dict[tuple[str, str], dict] = {}
    for row in res.data or []:
        key = (row["carrier_id"], row["truck_id"])
        seen.setdefault(key, row)
    return {"count": len(seen), "items": list(seen.values())}


@router.get("/hos")
def latest_hos(carrier_id: str | None = None, limit: int = 200) -> dict:
    """Latest HOS record per driver — powers the Fleet Map panel."""
    q = (
        get_supabase()
        .table("driver_hos_status")
        .select("*")
        .order("ts", desc=True)
        .limit(limit * 10)
    )
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    rows = q.execute().data or []
    seen: dict[tuple, dict] = {}
    for row in rows:
        key = (row.get("carrier_id"), row.get("driver_code") or row.get("driver_id", ""))
        seen.setdefault(key, row)
    return {"count": len(seen), "items": list(seen.values())[:limit]}


@router.post("/hos")
def update_hos(status: HosStatus) -> dict:
    get_supabase().table("driver_hos_status").insert(status.model_dump(exclude_none=True)).execute()
    return {"ok": True}


# ── Native / Browser-GPS endpoints ───────────────────────────────────────────

@router.post("/native-ping")
def native_ping(ping: NativePing) -> dict:
    """Accept a GPS ping from the driver-tracker PWA (browser geolocation).

    Maps the native payload to the ``truck_telemetry`` schema and also upserts
    HOS status when ``duty_status`` is present.
    """
    sb = get_supabase()
    now = datetime.now(timezone.utc).isoformat()

    tel_row = {
        "truck_id":       ping.truck_id,
        "carrier_id":     ping.carrier_id or ping.truck_id,
        "eld_provider":   "native",
        "lat":            ping.lat,
        "lng":            ping.lng,
        "speed_mph":      ping.speed_mph,
        "heading":        ping.heading_deg,
        "ts":             ping.ts.isoformat() if ping.ts else now,
    }
    # strip None values
    tel_row = {k: v for k, v in tel_row.items() if v is not None}

    try:
        sb.table("truck_telemetry").insert(tel_row).execute()
    except Exception as e:
        log.error("native_ping truck_telemetry insert failed: %s", e)
        raise HTTPException(500, f"telemetry insert failed: {e}")

    if ping.duty_status:
        hos_row = {
            "carrier_id":  ping.carrier_id or ping.truck_id,
            "driver_code": ping.driver_name or ping.truck_id,
            "truck_id":    ping.truck_id,
            "duty_status": ping.duty_status,
            "ts":          ping.ts.isoformat() if ping.ts else now,
        }
        try:
            sb.table("driver_hos_status").insert(hos_row).execute()
        except Exception as e:
            log.warning("native_ping hos insert failed: %s", e)

    return {"ok": True, "ts": now}


@router.get("/driver-summary")
def driver_summary(carrier_id: str | None = None, limit: int = 100) -> dict:
    """Return one summary row per truck_id tracked via the native-ping endpoint.

    Each row includes the latest position, last-seen timestamp, duty status,
    and a rough ping count (capped at ``limit * 10`` raw rows scanned).
    """
    sb = get_supabase()
    q = (
        sb.table("truck_telemetry")
        .select("carrier_id,truck_id,lat,lng,speed_mph,heading,ts")
        .eq("eld_provider", "native")
        .order("ts", desc=True)
        .limit(limit * 10)
    )
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    rows = q.execute().data or []

    # latest position per truck
    seen: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for row in rows:
        k = row["truck_id"]
        counts[k] = counts.get(k, 0) + 1
        seen.setdefault(k, row)

    # pull latest HOS for each truck
    hos_q = (
        sb.table("driver_hos_status")
        .select("truck_id,driver_code,duty_status,ts")
        .order("ts", desc=True)
        .limit(limit * 10)
    )
    if carrier_id:
        hos_q = hos_q.eq("carrier_id", carrier_id)
    hos_rows = hos_q.execute().data or []
    hos_by_truck: dict[str, dict] = {}
    for h in hos_rows:
        if h.get("truck_id"):
            hos_by_truck.setdefault(h["truck_id"], h)

    items = []
    for truck_id, row in list(seen.items())[:limit]:
        hos = hos_by_truck.get(truck_id, {})
        items.append({
            **row,
            "ping_count":   counts.get(truck_id, 1),
            "duty_status":  hos.get("duty_status"),
            "driver_name":  hos.get("driver_code"),
        })

    return {"count": len(items), "items": items}


@router.get("/driver/{driver_code}/history")
def driver_ping_history(
    driver_code: str,
    limit: int = 200,
    carrier_id: str | None = None,
) -> dict:
    """Return recent ping history for a single driver / truck (identified by ``driver_code`` or truck_id).

    Searches ``truck_telemetry`` where ``truck_id = driver_code`` so the
    driver-tracker PWA (which sets truck_id to whatever the driver enters)
    integrates seamlessly.
    """
    sb = get_supabase()
    q = (
        sb.table("truck_telemetry")
        .select("truck_id,lat,lng,speed_mph,heading,ts")
        .eq("truck_id", driver_code)
        .order("ts", desc=True)
        .limit(limit)
    )
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    rows = q.execute().data or []
    return {"driver_code": driver_code, "count": len(rows), "history": rows}


@router.delete("/driver/{driver_code}/session")
def clear_driver_session(driver_code: str, carrier_id: str | None = None) -> dict:
    """Delete all native-ping telemetry rows for a driver / truck.

    Useful when a driver hands the device to a new driver or a truck changes
    assignment.  Only removes rows where ``eld_provider = 'native'``.
    """
    sb = get_supabase()
    q = (
        sb.table("truck_telemetry")
        .delete()
        .eq("truck_id", driver_code)
        .eq("eld_provider", "native")
    )
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    try:
        res = q.execute()
        deleted = len(res.data) if res.data else 0
    except Exception as e:
        log.error("clear_driver_session failed: %s", e)
        raise HTTPException(500, f"delete failed: {e}")

    log.info("clear_driver_session: deleted %d rows for driver_code=%s", deleted, driver_code)
    return {"ok": True, "deleted": deleted, "driver_code": driver_code}

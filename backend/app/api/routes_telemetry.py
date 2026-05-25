"""Telemetry + HOS — powers the EAGLE EYE live map and HOS widgets."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..logging_service import get_logger
from ..models.telemetry import HosStatus, TelemetryPing
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


@router.post("/hos")
def update_hos(status: HosStatus) -> dict:
    get_supabase().table("driver_hos_status").insert(status.model_dump(exclude_none=True)).execute()
    return {"ok": True}

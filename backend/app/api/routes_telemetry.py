"""Telemetry + HOS — powers the EAGLE EYE live map and HOS widgets."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..logging_service import get_logger
from ..models.telemetry import HosStatus, TelemetryPing
from ..settings import get_settings
from ..supabase_client import get_supabase
from .deps import require_bearer

log = get_logger("route.telemetry")

router = APIRouter(dependencies=[Depends(require_bearer)])


# ─── existing endpoints ────────────────────────────────────────────────────────

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


# ─── new endpoints ─────────────────────────────────────────────────────────────

class NativePingBody(BaseModel):
    truck_id: str
    carrier_id: str | None = None
    lat: float
    lng: float
    speed_mph: float | None = None
    heading_deg: float | None = None
    driver_name: str | None = None
    duty_status: str | None = None
    accuracy_m: float | None = None


@router.post("/native-ping")
def native_ping(body: NativePingBody) -> dict:
    """Browser-based GPS ping from driver-tracker.html. carrier_id is optional."""
    now_ts = datetime.now(timezone.utc).isoformat()
    row: dict[str, Any] = {
        "truck_id":     body.truck_id,
        "carrier_id":   body.carrier_id or body.truck_id,
        "eld_provider": "native_gps",
        "lat":          body.lat,
        "lng":          body.lng,
        "ts":           now_ts,
    }
    if body.speed_mph is not None:
        row["speed_mph"] = body.speed_mph
    if body.heading_deg is not None:
        row["heading"] = body.heading_deg

    try:
        get_supabase().table("truck_telemetry").insert(row).execute()
    except Exception as e:
        log.error("native_ping insert failed: %s", e)
        raise HTTPException(500, f"telemetry insert failed: {e}")

    # Also update HOS if duty_status provided
    if body.duty_status:
        try:
            hos_row = {
                "carrier_id":  body.carrier_id or body.truck_id,
                "driver_code": body.driver_name or body.truck_id,
                "duty_status": body.duty_status,
                "ts":          now_ts,
            }
            get_supabase().table("driver_hos_status").insert(hos_row).execute()
        except Exception as e:
            log.warning("native_ping HOS insert failed (non-fatal): %s", e)

    return {"ok": True, "ts": now_ts}


@router.post("/pull")
async def pull_eld() -> dict:
    """Active polling of all verified ELD integrations. Normalises to TelemetryPing rows."""
    settings = get_settings()
    sb = get_supabase()

    # Load verified/active ELD connections
    try:
        conn_res = (
            sb.table("eld_connections")
            .select("*")
            .in_("status", ["verified", "active"])
            .execute()
        )
        connections: list[dict] = conn_res.data or []
    except Exception as e:
        log.warning("eld_connections fetch failed, falling back to settings: %s", e)
        connections = []

    pulled = 0
    providers_seen: list[str] = []
    errors: list[str] = []
    now_ts = datetime.now(timezone.utc).isoformat()

    async with httpx.AsyncClient(timeout=15.0) as client:

        # ── Per-connection pulling ──────────────────────────────────────────
        for conn in connections:
            provider = (conn.get("provider") or "").lower()
            token    = conn.get("eld_api_token") or conn.get("api_token") or ""
            carrier  = conn.get("carrier_id") or ""
            if not token:
                continue

            try:
                rows = await _fetch_provider(client, provider, token, conn, carrier, now_ts)
                if rows:
                    sb.table("truck_telemetry").insert(rows).execute()
                    pulled += len(rows)
                    if provider not in providers_seen:
                        providers_seen.append(provider)
            except Exception as e:
                msg = f"{provider}: {e}"
                log.error("ELD pull error — %s", msg)
                errors.append(msg)

        # ── Settings-level fallback (no eld_connections rows yet) ──────────
        if settings.motive_api_key and "motive" not in providers_seen:
            try:
                rows = await _fetch_motive(client, settings.motive_api_key, "", now_ts)
                if rows:
                    sb.table("truck_telemetry").insert(rows).execute()
                    pulled += len(rows)
                    providers_seen.append("motive")
            except Exception as e:
                errors.append(f"motive(settings): {e}")

        if settings.samsara_api_key and "samsara" not in providers_seen:
            try:
                rows = await _fetch_samsara(client, settings.samsara_api_key, "", now_ts)
                if rows:
                    sb.table("truck_telemetry").insert(rows).execute()
                    pulled += len(rows)
                    providers_seen.append("samsara")
            except Exception as e:
                errors.append(f"samsara(settings): {e}")

        if settings.geotab_username and settings.geotab_password and "geotab" not in providers_seen:
            try:
                rows = await _fetch_geotab(
                    client,
                    settings.geotab_username,
                    settings.geotab_password,
                    "",
                    now_ts,
                )
                if rows:
                    sb.table("truck_telemetry").insert(rows).execute()
                    pulled += len(rows)
                    providers_seen.append("geotab")
            except Exception as e:
                errors.append(f"geotab(settings): {e}")

    return {"ok": True, "pulled": pulled, "providers": providers_seen, "errors": errors}


async def _fetch_provider(
    client: httpx.AsyncClient,
    provider: str,
    token: str,
    conn: dict,
    carrier_id: str,
    now_ts: str,
) -> list[dict]:
    if provider == "motive":
        return await _fetch_motive(client, token, carrier_id, now_ts)
    if provider == "samsara":
        return await _fetch_samsara(client, token, carrier_id, now_ts)
    if provider == "geotab":
        username = conn.get("username") or ""
        password = conn.get("password") or ""
        database = conn.get("account_id") or ""
        return await _fetch_geotab(client, username, password, carrier_id, now_ts, database)
    return []


async def _fetch_motive(
    client: httpx.AsyncClient, token: str, carrier_id: str, now_ts: str
) -> list[dict]:
    r = await client.get(
        "https://api.gomotive.com/v1/vehicle_locations",
        headers={"Authorization": f"Token {token}"},
    )
    r.raise_for_status()
    data = r.json()
    rows = []
    for v in data.get("vehicles", []):
        loc = v.get("current_location") or {}
        lat = loc.get("lat")
        lng = loc.get("lon")
        if lat is None or lng is None:
            continue
        rows.append({
            "truck_id":     str(v.get("id", "")),
            "carrier_id":   carrier_id or "motive",
            "eld_provider": "motive",
            "lat":          float(lat),
            "lng":          float(lng),
            "speed_mph":    float(loc["speed"]) if loc.get("speed") is not None else None,
            "heading":      float(loc["heading"]) if loc.get("heading") is not None else None,
            "ts":           now_ts,
        })
    return rows


async def _fetch_samsara(
    client: httpx.AsyncClient, token: str, carrier_id: str, now_ts: str
) -> list[dict]:
    r = await client.get(
        "https://api.samsara.com/fleet/vehicles/locations",
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    data = r.json()
    rows = []
    for v in data.get("data", []):
        loc = v.get("location") or {}
        lat = loc.get("latitude")
        lng = loc.get("longitude")
        if lat is None or lng is None:
            continue
        rows.append({
            "truck_id":     str(v.get("id", "")),
            "carrier_id":   carrier_id or "samsara",
            "eld_provider": "samsara",
            "lat":          float(lat),
            "lng":          float(lng),
            "speed_mph":    float(loc["speedMilesPerHour"]) if loc.get("speedMilesPerHour") is not None else None,
            "heading":      float(loc["headingDegrees"])    if loc.get("headingDegrees")    is not None else None,
            "ts":           now_ts,
        })
    return rows


async def _fetch_geotab(
    client: httpx.AsyncClient,
    username: str,
    password: str,
    carrier_id: str,
    now_ts: str,
    database: str = "db",
) -> list[dict]:
    payload = {
        "method": "Get",
        "params": {
            "typeName": "DeviceStatusInfo",
            "credentials": {
                "database": database or "db",
                "userName": username,
                "password": password,
            },
        },
    }
    r = await client.post("https://my.geotab.com/apiv1", json=payload)
    r.raise_for_status()
    data = r.json()
    rows = []
    for item in data.get("result", []):
        lat = item.get("latitude")
        lng = item.get("longitude")
        if lat is None or lng is None:
            continue
        device = item.get("device") or {}
        rows.append({
            "truck_id":     str(device.get("id", item.get("id", ""))),
            "carrier_id":   carrier_id or "geotab",
            "eld_provider": "geotab",
            "lat":          float(lat),
            "lng":          float(lng),
            "speed_mph":    float(item["speed"]) if item.get("speed") is not None else None,
            "ts":           now_ts,
        })
    return rows


@router.get("/driver-link")
def driver_link(
    request: Request,
    carrier_id: str = "",
    truck_id: str = "",
    driver_name: str = "",
) -> dict:
    """Generate a shareable driver tracking link."""
    if not truck_id:
        raise HTTPException(400, "truck_id is required")

    base = str(request.base_url).rstrip("/")
    params = f"?truck={truck_id}"
    if carrier_id:
        params += f"&carrier={carrier_id}"
    if driver_name:
        params += f"&name={driver_name}"

    url = f"{base}/driver-tracker.html{params}"
    return {"ok": True, "url": url}


class VerifyEldBody(BaseModel):
    provider: str
    api_token: str
    account_id: str | None = None


@router.post("/verify-eld")
async def verify_eld(body: VerifyEldBody) -> dict:
    """Test ELD credentials without persisting anything."""
    provider = body.provider.lower().strip()

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            if provider == "motive":
                r = await client.get(
                    "https://api.gomotive.com/v1/users/me",
                    headers={"Authorization": f"Token {body.api_token}"},
                )
                valid = r.status_code == 200
                message = "Motive credentials valid" if valid else f"Motive returned {r.status_code}"
                vehicle_count: int | None = None
                if valid:
                    try:
                        vr = await client.get(
                            "https://api.gomotive.com/v1/vehicle_locations",
                            headers={"Authorization": f"Token {body.api_token}"},
                        )
                        if vr.status_code == 200:
                            vehicle_count = len(vr.json().get("vehicles", []))
                    except Exception:
                        pass
                return {"ok": True, "valid": valid, "message": message, "vehicle_count": vehicle_count}

            elif provider == "samsara":
                r = await client.get(
                    "https://api.samsara.com/me",
                    headers={"Authorization": f"Bearer {body.api_token}"},
                )
                valid = r.status_code == 200
                message = "Samsara credentials valid" if valid else f"Samsara returned {r.status_code}"
                vehicle_count = None
                if valid:
                    try:
                        vr = await client.get(
                            "https://api.samsara.com/fleet/vehicles/locations",
                            headers={"Authorization": f"Bearer {body.api_token}"},
                        )
                        if vr.status_code == 200:
                            vehicle_count = len(vr.json().get("data", []))
                    except Exception:
                        pass
                return {"ok": True, "valid": valid, "message": message, "vehicle_count": vehicle_count}

            else:
                return {
                    "ok": True,
                    "valid": False,
                    "message": f"Provider '{provider}' verification not supported. Use 'motive' or 'samsara'.",
                    "vehicle_count": None,
                }

        except httpx.RequestError as e:
            log.warning("verify-eld request error: %s", e)
            return {"ok": True, "valid": False, "message": f"Connection error: {e}", "vehicle_count": None}

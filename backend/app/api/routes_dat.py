"""DAT load board API integration — fetch available loads, transform to Supabase schema."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..logging_service import get_logger
from ..settings import get_settings
from ..supabase_client import get_supabase
from ..utils.load_transformer import transform_dat_load
from .deps import require_bearer

log = get_logger("dat.routes")
router = APIRouter(dependencies=[Depends(require_bearer)])


# ── DAT connection status ─────────────────────────────────────────────────────

@router.get("/dat/status")
def dat_status() -> dict:
    """Returns whether DAT credentials are configured."""
    s = get_settings()
    configured = bool(s.dat_client_id and s.dat_client_secret)
    return {"configured": configured, "client_id_hint": (s.dat_client_id or "")[:6] + "…" if configured else None}


# ── Truck Postings (stored in Supabase; synced to DAT when credentials live) ──

@router.get("/dat/posts")
def list_dat_posts(
    status_filter: str | None = Query(None, alias="status"),
    carrier_id: str | None = None,
    limit: int = 200,
) -> dict:
    sb = get_supabase()
    q = sb.table("dat_truck_posts").select("*").order("created_at", desc=True).limit(limit)
    if status_filter:
        q = q.eq("status", status_filter)
    if carrier_id:
        q = q.eq("carrier_id", carrier_id)
    res = q.execute()
    return {"count": len(res.data or []), "items": res.data or []}


@router.post("/dat/posts", status_code=201)
async def create_dat_post(payload: dict) -> dict:
    """Post a truck to DAT (stored in Supabase; also calls DAT API if credentials configured)."""
    sb = get_supabase()
    payload["status"] = "active"
    payload["posted_to_dat"] = False

    # Attempt live DAT posting if credentials are available
    s = get_settings()
    if s.dat_client_id and s.dat_client_secret:
        try:
            token = await _get_dat_token(s.dat_client_id, s.dat_client_secret)
            dat_body = {
                "equipment": payload.get("equipment_type", "Dry Van"),
                "availableDate": payload.get("available_date"),
                "origin": {
                    "zip": payload.get("origin_zip", ""),
                    "city": payload.get("origin_city", ""),
                    "state": payload.get("origin_state", ""),
                },
                "deadheadMiles": payload.get("miles_willing", 500),
                "contact": {
                    "name": payload.get("contact_name", ""),
                    "phone": payload.get("contact_phone", ""),
                },
            }
            if payload.get("dest_city"):
                dat_body["destination"] = {"city": payload["dest_city"], "state": payload.get("dest_state", "")}

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.dat.com/power/v2/offers/trucks",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=dat_body,
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    payload["dat_post_id"] = data.get("id") or data.get("postingId")
                    payload["posted_to_dat"] = True
                    log.info("Posted truck to DAT: %s", payload["dat_post_id"])
        except Exception as exc:  # noqa: BLE001
            log.warning("DAT live post failed (stored locally): %s", exc)

    res = sb.table("dat_truck_posts").insert(payload).execute()
    return {"ok": True, "item": res.data[0] if res.data else {}, "posted_to_dat": payload["posted_to_dat"]}


@router.patch("/dat/posts/{post_id}")
async def update_dat_post(post_id: str, payload: dict) -> dict:
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    get_supabase().table("dat_truck_posts").update(payload).eq("id", post_id).execute()
    return {"ok": True}


@router.delete("/dat/posts/{post_id}")
async def cancel_dat_post(post_id: str) -> dict:
    """Cancel a truck posting — removes from DAT if posted live, marks cancelled in Supabase."""
    sb = get_supabase()
    row = sb.table("dat_truck_posts").select("dat_post_id,posted_to_dat").eq("id", post_id).limit(1).execute()
    if row.data and row.data[0].get("posted_to_dat") and row.data[0].get("dat_post_id"):
        s = get_settings()
        if s.dat_client_id and s.dat_client_secret:
            try:
                token = await _get_dat_token(s.dat_client_id, s.dat_client_secret)
                dat_post_id = row.data[0]["dat_post_id"]
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.delete(
                        f"https://api.dat.com/power/v2/offers/trucks/{dat_post_id}",
                        headers={"Authorization": f"Bearer {token}"},
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("DAT delete post failed: %s", exc)
    sb.table("dat_truck_posts").update({
        "status": "cancelled",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", post_id).execute()
    return {"ok": True}


# ── Load Search (search DAT for available freight) ────────────────────────────

@router.post("/dat/search")
async def search_dat_loads(
    origin: str | None = None,
    destination: str | None = None,
    equipment: str | None = None,
    radius: int = 150,
    min_rate: int = 0,
) -> dict:
    """Search DAT for available loads. Falls back to an empty list if credentials not configured."""
    s = get_settings()
    if not s.dat_client_id or not s.dat_client_secret:
        return {"ok": True, "configured": False, "loads": [], "message": "DAT credentials not configured — add DAT_CLIENT_ID and DAT_CLIENT_SECRET to .env"}

    try:
        token = await _get_dat_token(s.dat_client_id, s.dat_client_secret)
        params: dict = {"limit": 50}
        if origin:
            params["originCity"] = origin
        if destination:
            params["destinationCity"] = destination
        if equipment:
            params["equipment"] = equipment
        if radius:
            params["radius"] = radius
        if min_rate > 0:
            params["minRate"] = min_rate

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://api.dat.com/power/v2/loads",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            if resp.status_code != 200:
                log.error("DAT search failed: %s", resp.text)
                return {"ok": False, "configured": True, "loads": [], "message": f"DAT API error: {resp.status_code}"}
            data = resp.json()
            return {"ok": True, "configured": True, "loads": data.get("loads", []), "total": data.get("total", 0)}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.error("DAT search exception: %s", exc)
        return {"ok": False, "configured": True, "loads": [], "message": str(exc)}


@router.post("/fetch-dat")
async def fetch_dat_loads(
    distance_from_zip: str | None = Query(None, description="Starting zipcode"),
    radius_miles: int = Query(500, description="Search radius"),
    equipment_types: list[str] | None = Query(None, description="Equipment filters"),
    min_rate: int = Query(0, description="Minimum rate in dollars"),
) -> dict:
    """Fetch available loads from DAT load board, transform and store in Supabase."""
    s = get_settings()

    if not s.dat_client_id or not s.dat_client_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "DAT credentials not configured")

    try:
        # Step 1: Get OAuth token from DAT
        token = await _get_dat_token(s.dat_client_id, s.dat_client_secret)

        # Step 2: Query DAT API for available loads
        params: dict = {
            "limit": 100,
            "status": "available",
        }

        if distance_from_zip:
            params["origin_zip"] = distance_from_zip
            params["radius"] = radius_miles

        if equipment_types:
            params["equipment"] = ",".join(equipment_types)

        if min_rate > 0:
            params["min_rate"] = min_rate

        dat_response = await _query_dat_loads(token, params)

        if not dat_response:
            return {"ok": True, "imported": 0, "loads": []}

        # Step 3: Transform and insert into Supabase
        sb = get_supabase()
        imported_count = 0
        imported_loads = []

        for dat_load in dat_response:
            try:
                transformed = transform_dat_load(dat_load)

                # Check for duplicate by source_id
                existing = (
                    sb.table("loads")
                    .select("id")
                    .eq("source_id", transformed["source_id"])
                    .execute()
                )

                if existing.data:
                    log.info(f"DAT load {transformed['source_id']} already exists, skipping")
                    continue

                # Insert into Supabase
                result = sb.table("loads").insert(transformed).execute()

                if result.data:
                    imported_loads.append(result.data[0])
                    imported_count += 1
                    log.info(f"Imported DAT load: {transformed.get('load_number')}")

            except Exception as e:  # noqa: BLE001
                log.error(f"Failed to import DAT load: {e}")
                # Continue importing other loads on error

        return {
            "ok": True,
            "imported": imported_count,
            "loads": imported_loads,
            "source": "dat",
        }

    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"DAT load fetch failed: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


@router.get("/dat-boards")
async def list_dat_boards() -> dict:
    """List available load boards/equipment types from DAT."""
    s = get_settings()

    if not s.dat_client_id or not s.dat_client_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "DAT credentials not configured")

    try:
        token = await _get_dat_token(s.dat_client_id, s.dat_client_secret)

        # Query DAT for available boards/equipment
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://api.dat.com/v1/equipment",
                headers={"Authorization": f"Bearer {token}"},
            )

            if response.status_code != 200:
                log.error(f"DAT boards query failed: {response.text}")
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "DAT API error")

            data = response.json()

            return {
                "ok": True,
                "boards": data.get("equipment_types", []),
            }

    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        log.error(f"DAT boards lookup failed: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))


async def _get_dat_token(client_id: str, client_secret: str) -> str:
    """Get OAuth2 token from DAT API."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.dat.com/v1/token",
                auth=(client_id, client_secret),
                data={"grant_type": "client_credentials"},
            )

            if response.status_code != 200:
                log.error(f"DAT auth failed: {response.text}")
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "DAT authentication failed")

            data = response.json()
            return data.get("access_token")

    except httpx.RequestError as e:
        log.error(f"DAT token request failed: {e}")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "DAT API unreachable")


async def _query_dat_loads(token: str, params: dict) -> list[dict]:
    """Query DAT API for available loads."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                "https://api.dat.com/v1/loads",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )

            if response.status_code != 200:
                log.error(f"DAT loads query failed: {response.text}")
                return []

            data = response.json()
            return data.get("loads", [])

    except httpx.RequestError as e:
        log.error(f"DAT loads request failed: {e}")
        return []

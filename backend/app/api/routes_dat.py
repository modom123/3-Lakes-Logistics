"""DAT load board API integration — fetch available loads, transform to Supabase schema."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query, status

from ..logging_service import get_logger
from ..settings import get_settings
from ..supabase_client import get_supabase
from ..utils.load_transformer import transform_dat_load
from .deps import require_bearer

log = get_logger("dat.routes")
router = APIRouter(dependencies=[require_bearer()])


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

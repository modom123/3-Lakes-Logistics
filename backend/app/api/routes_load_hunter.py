"""Load Hunter API — trigger scans, fetch results, manage config.

Endpoints (all bearer-protected):
  POST /api/load-hunter/hunt      — run an immediate scan
  GET  /api/load-hunter/results   — recent hits
  GET  /api/load-hunter/status    — last run, config, board health
  POST /api/load-hunter/config    — save hunt configuration
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..logging_service import get_logger
from .deps import require_bearer

log    = get_logger("load_hunter.api")
router = APIRouter(dependencies=[Depends(require_bearer)])


class HuntRequest(BaseModel):
    origin_city:  str = "Portland"
    origin_state: str = "OR"
    origin_zip:   str = "97201"
    max_dh_miles: int = 100
    min_rpm:      float = 1.00
    hot_rpm:      float = 2.00
    trailer_type: str = "cargo_van"
    boards:       list[str] = ["123loadboard", "dat", "truckstop", "truckerpath"]


class ConfigRequest(BaseModel):
    origin_city:  str | None = None
    origin_state: str | None = None
    origin_zip:   str | None = None
    max_dh_miles: int | None = None
    min_rpm:      float | None = None
    hot_rpm:      float | None = None
    trailer_type: str | None = None
    boards:       list[str] | None = None


@router.post("/hunt")
async def trigger_hunt(body: HuntRequest) -> dict:
    """Immediately run a load hunt across all configured boards."""
    from ..agents.load_hunter import hunt
    cfg = {k: v for k, v in body.model_dump().items() if v is not None}
    return hunt(cfg)


@router.get("/results")
def get_results(limit: int = 200) -> dict:
    """Return recent load hunter hits from the database."""
    from ..agents.load_hunter import results
    return results(limit)


@router.get("/status")
def get_status() -> dict:
    """Return last hunt time, current config, and board health."""
    from ..agents.load_hunter import status
    return status()


@router.post("/config")
def save_config(body: ConfigRequest) -> dict:
    """Persist hunt configuration."""
    from ..agents.load_hunter import _load_config, _save_config
    current = _load_config()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    _save_config({**current, **updates})
    return {"ok": True, "config": {**current, **updates}}

"""Load Hunter — relentless multi-board load scanner.

Scans 123loadboard (+ DAT, Truckstop, TruckerPath) continuously for loads
matching configured criteria and stores hits in `load_hunter_results`.

Default hunt config (Portland, OR):
  origin_city   = "Portland"
  origin_state  = "OR"
  origin_zip    = "97201"
  max_dh_miles  = 100
  min_rpm       = 1.00
  trailer_type  = "cargo_van"

Actions:
  hunt        — run one full scan across all configured boards
  results     — fetch recent hits
  status      — last run time + total hits
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from ..logging_service import get_logger, log_agent
from ..supabase_client import get_supabase
from . import memory as mem

log = get_logger("load_hunter")
_NAME = "load_hunter"

# ── Default hunt profile (Portland light fleet) ───────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "origin_city":   "Portland",
    "origin_state":  "OR",
    "origin_zip":    "97201",
    "max_dh_miles":  100,
    "min_rpm":       1.00,
    "trailer_type":  "cargo_van",
    "boards":        ["123loadboard", "dat", "truckstop", "truckerpath", "ch_robinson"],
    "hot_rpm":       2.00,   # loads above this are flagged HOT 🔥
    "limit_per_board": 50,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db():
    try:
        return get_supabase()
    except Exception:
        return None


def _load_config() -> dict[str, Any]:
    """Load hunt config from memory, falling back to defaults."""
    cfg = mem.recall(_NAME, "hunt_config")
    if cfg and isinstance(cfg, dict):
        return {**DEFAULT_CONFIG, **cfg}
    return dict(DEFAULT_CONFIG)


def _save_config(cfg: dict[str, Any]) -> None:
    mem.remember(
        _NAME, "hunt_config", cfg, confidence=1.0,
        summary=f"Hunt: {cfg.get('origin_city')}, {cfg.get('origin_state')} | "
                f"DH≤{cfg.get('max_dh_miles')}mi | RPM≥${cfg.get('min_rpm')}",
    )


def _rpm(load) -> float:
    """Compute rate per mile — prefer field value, calculate if needed."""
    rpm = getattr(load, "rate_per_mile", None) or 0.0
    if not rpm:
        rate  = float(getattr(load, "rate_total",  None) or 0)
        miles = float(getattr(load, "miles",       None) or 0)
        if rate and miles:
            rpm = rate / miles
    return round(float(rpm), 3)


def hunt(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run one full scan across all configured boards. Returns matching loads."""
    cfg = {**_load_config(), **(config or {})}

    from ..prospecting.loadboard_clients import (
        SearchParams,
        loadboard123_search,
    )

    try:
        from ..prospecting.loadboard_clients import (
            dat_search,
            truckstop_search,
            truckerpath_search,
            chrobinson_search,
        )
        extra_clients = {
            "dat": dat_search,
            "truckstop": truckstop_search,
            "truckerpath": truckerpath_search,
            "ch_robinson": chrobinson_search,
        }
    except ImportError:
        extra_clients = {}

    params = SearchParams(
        origin_state   = cfg["origin_state"],
        origin_city    = cfg["origin_city"],
        origin_zip     = cfg["origin_zip"],
        trailer_type   = cfg["trailer_type"],
        max_deadhead_mi= int(cfg["max_dh_miles"]),
        min_rate_per_mile=float(cfg["min_rpm"]),
    )

    boards_cfg = cfg.get("boards", ["123loadboard"])
    all_results: list[dict] = []
    board_stats: dict[str, int] = {}
    min_rpm = float(cfg["min_rpm"])
    hot_rpm = float(cfg["hot_rpm"])

    # ── 123loadboard ─────────────────────────────────────────────────────────
    if "123loadboard" in boards_cfg:
        try:
            raw = loadboard123_search(params)
            hits = [r for r in raw if _rpm(r) >= min_rpm]
            board_stats["123loadboard"] = len(hits)
            all_results.extend([_to_dict(r, hot_rpm) for r in hits])
        except Exception as exc:
            log.warning("123loadboard search failed: %s", exc)
            board_stats["123loadboard"] = 0

    # ── Other boards ──────────────────────────────────────────────────────────
    for board, fn in extra_clients.items():
        if board not in boards_cfg:
            continue
        try:
            raw = fn(params)
            hits = [r for r in raw if _rpm(r) >= min_rpm]
            board_stats[board] = len(hits)
            all_results.extend([_to_dict(r, hot_rpm) for r in hits])
        except Exception as exc:
            log.warning("%s search failed: %s", board, exc)
            board_stats[board] = 0

    # ── De-duplicate by load_id ───────────────────────────────────────────────
    seen: set[str] = set()
    unique: list[dict] = []
    for r in sorted(all_results, key=lambda x: x["rpm"], reverse=True):
        key = f"{r['source']}:{r['load_id']}"
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # ── Persist to DB ─────────────────────────────────────────────────────────
    db = _db()
    saved = 0
    if db and unique:
        for load in unique:
            try:
                db.table("load_hunter_results").upsert({
                    "source":        load["source"],
                    "load_id":       load["load_id"],
                    "broker_name":   load["broker_name"],
                    "origin_city":   load["origin_city"],
                    "origin_state":  load["origin_state"],
                    "dest_city":     load["dest_city"],
                    "dest_state":    load["dest_state"],
                    "miles":         load["miles"],
                    "rate_total":    load["rate_total"],
                    "rpm":           load["rpm"],
                    "trailer_type":  load["trailer_type"],
                    "pickup_date":   load["pickup_date"],
                    "is_hot":        load["is_hot"],
                    "hunt_config":   json.dumps({
                        "origin": f"{cfg['origin_city']}, {cfg['origin_state']}",
                        "max_dh": cfg["max_dh_miles"],
                        "min_rpm": cfg["min_rpm"],
                    }),
                    "found_at":      _now(),
                }, on_conflict="source,load_id").execute()
                saved += 1
            except Exception as exc:
                log.debug("load_hunter upsert failed: %s", exc)

    hot_count = sum(1 for r in unique if r["is_hot"])

    mem.remember(
        _NAME, "last_hunt",
        {"total": len(unique), "hot": hot_count, "boards": board_stats, "at": _now()},
        confidence=1.0,
        summary=f"Hunt: {len(unique)} loads found ({hot_count} HOT 🔥) from {cfg['origin_city']}, {cfg['origin_state']}",
    )
    log_agent(_NAME, "hunt", payload={"config": cfg}, result=f"found={len(unique)} hot={hot_count}")

    return {
        "ok":       True,
        "total":    len(unique),
        "hot":      hot_count,
        "loads":    unique,
        "boards":   board_stats,
        "origin":   f"{cfg['origin_city']}, {cfg['origin_state']}",
        "min_rpm":  min_rpm,
        "hunted_at": _now(),
    }


def results(limit: int = 100) -> dict[str, Any]:
    """Fetch recent hunt results from DB."""
    db = _db()
    if not db:
        return {"error": "db_unavailable"}
    try:
        rows = (
            db.table("load_hunter_results")
            .select("*")
            .order("found_at", desc=True)
            .limit(limit)
            .execute()
            .data or []
        )
        return {"total": len(rows), "loads": rows}
    except Exception as e:
        return {"error": str(e)}


def status() -> dict[str, Any]:
    last = mem.recall(_NAME, "last_hunt") or {}
    cfg  = _load_config()
    return {
        "last_hunt":   last,
        "config":      cfg,
        "boards_live": cfg.get("boards", []),
    }


def _to_dict(r: Any, hot_rpm: float) -> dict:
    rpm = _rpm(r)
    return {
        "source":      r.source,
        "load_id":     r.load_id,
        "broker_name": r.broker_name,
        "origin_city": r.origin_city,
        "origin_state":r.origin_state,
        "dest_city":   r.dest_city,
        "dest_state":  r.dest_state,
        "miles":       r.miles,
        "rate_total":  r.rate_total,
        "rpm":         rpm,
        "trailer_type":r.trailer_type,
        "pickup_date": r.pickup_date,
        "is_hot":      rpm >= hot_rpm,
    }


def hunt_for_driver(driver_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a load hunt scoped to a specific driver using their agent card fields."""
    db = _db()
    if not db:
        return {"error": "db_unavailable", "driver_id": driver_id}

    res = db.table("light_vehicle_drivers").select("*").eq("id", driver_id).execute()
    if not res.data:
        return {"error": "driver_not_found", "driver_id": driver_id}

    d = res.data[0]

    # Build hunt config from driver card, then apply any caller overrides
    service_areas: list = d.get("service_areas") or []
    # Use first service area city/state if provided (format: "Portland, OR")
    origin_city  = DEFAULT_CONFIG["origin_city"]
    origin_state = DEFAULT_CONFIG["origin_state"]
    origin_zip   = DEFAULT_CONFIG["origin_zip"]
    if service_areas:
        parts = [p.strip() for p in service_areas[0].split(",")]
        if len(parts) >= 2:
            origin_city  = parts[0]
            origin_state = parts[1]

    driver_cfg: dict[str, Any] = {
        "origin_city":   origin_city,
        "origin_state":  origin_state,
        "origin_zip":    origin_zip,
        "max_dh_miles":  d.get("max_deadhead_mi") or DEFAULT_CONFIG["max_dh_miles"],
        "min_rpm":       float(d.get("min_rpm") or DEFAULT_CONFIG["min_rpm"]),
        "trailer_type":  d.get("vehicle_cargo_type") or d.get("vehicle_type") or DEFAULT_CONFIG["trailer_type"],
    }
    if overrides:
        driver_cfg.update(overrides)

    result = hunt(driver_cfg)

    # Tag all matched loads with this driver_id and persist
    if db and result.get("loads"):
        for load in result["loads"]:
            try:
                db.table("load_hunter_results").upsert(
                    {"source": load["source"], "load_id": load["load_id"], "driver_id": driver_id},
                    on_conflict="source,load_id",
                ).execute()
            except Exception as exc:
                log.debug("tag driver_id failed: %s", exc)

        # Update driver's last_hunted_at and matched_loads_count
        try:
            db.table("light_vehicle_drivers").update({
                "last_hunted_at": _now(),
                "matched_loads_count": (d.get("matched_loads_count") or 0) + len(result["loads"]),
            }).eq("id", driver_id).execute()
        except Exception as exc:
            log.debug("driver stat update failed: %s", exc)

    log_agent(_NAME, "hunt_for_driver", payload={"driver_id": driver_id}, result=f"found={result.get('total',0)}")
    return {"agent": _NAME, "driver_id": driver_id, **result}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "hunt")).lower()

    if action == "hunt":
        cfg_override = {k: payload[k] for k in (
            "origin_city","origin_state","origin_zip",
            "max_dh_miles","min_rpm","trailer_type","boards","hot_rpm"
        ) if k in payload}
        return {"agent": _NAME, **hunt(cfg_override or None)}

    if action == "results":
        return {"agent": _NAME, **results(int(payload.get("limit", 100)))}

    if action == "status":
        return {"agent": _NAME, **status()}

    if action == "save_config":
        cfg = {k: payload[k] for k in DEFAULT_CONFIG if k in payload}
        if cfg:
            _save_config({**_load_config(), **cfg})
        return {"agent": _NAME, "ok": True, "saved": cfg}

    if action == "hunt_driver":
        driver_id = payload.get("driver_id")
        if not driver_id:
            return {"agent": _NAME, "error": "driver_id required"}
        overrides = {k: payload[k] for k in (
            "origin_city","origin_state","origin_zip",
            "max_dh_miles","min_rpm","trailer_type","boards",
        ) if k in payload}
        return hunt_for_driver(driver_id, overrides or None)

    return {"agent": _NAME, "error": f"unknown action: {action}"}

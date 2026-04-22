"""Google Maps directions + ETA cache (step 85)."""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from ..settings import get_settings

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 600  # 10 min


@dataclass
class Route:
    miles: float
    duration_min: float
    polyline: str
    provider: str = "gmaps"


def directions(origin: str, destination: str, mode: str = "driving") -> Route | None:
    s = get_settings()
    key = f"{origin}|{destination}|{mode}"
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL:
        d = hit[1]
        return Route(d["miles"], d["duration_min"], d["polyline"])
    if not s.google_maps_api_key:
        return None
    try:
        r = httpx.get(
            "https://maps.googleapis.com/maps/api/directions/json",
            params={"origin": origin, "destination": destination,
                    "mode": mode, "key": s.google_maps_api_key},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        route = (data.get("routes") or [{}])[0]
        leg = (route.get("legs") or [{}])[0]
        miles = (leg.get("distance", {}).get("value") or 0) / 1609.344
        duration_min = (leg.get("duration", {}).get("value") or 0) / 60.0
        poly = route.get("overview_polyline", {}).get("points") or ""
        payload = {"miles": miles, "duration_min": duration_min, "polyline": poly}
        _CACHE[key] = (now, payload)
        return Route(miles, duration_min, poly)
    except Exception:  # noqa: BLE001
        return None


def eta_minutes(origin: str, destination: str) -> float | None:
    r = directions(origin, destination)
    return r.duration_min if r else None

"""Orbit — Step 39. Geofence arrivals/departures at pickup/delivery."""
from __future__ import annotations

import math
from typing import Any

from ..logging_service import log_agent


GEOFENCE_RADIUS_MI = 0.50  # half-mile arrival detection


def haversine_mi(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def inside_fence(lat: float, lng: float, fence_lat: float, fence_lng: float,
                 radius_mi: float = GEOFENCE_RADIUS_MI) -> bool:
    return haversine_mi(lat, lng, fence_lat, fence_lng) <= radius_mi


def run(payload: dict[str, Any]) -> dict[str, Any]:
    arrived = inside_fence(
        payload["lat"], payload["lng"],
        payload["fence_lat"], payload["fence_lng"],
        payload.get("radius_mi", GEOFENCE_RADIUS_MI),
    )
    log_agent("orbit", "geofence_check", payload=payload, result="arrived" if arrived else "outside")
    return {"agent": "orbit", "arrived": arrived}

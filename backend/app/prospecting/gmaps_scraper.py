"""Step 42: Google Maps scraper for local carrier search."""
from __future__ import annotations

from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings

QUERIES = ["trucking company", "freight dispatch", "owner operator trucking"]


def search_area(lat: float, lng: float, radius_mi: int = 50) -> list[dict[str, Any]]:
    key = get_settings().google_maps_api_key
    if not key:
        return []
    results: list[dict[str, Any]] = []
    for q in QUERIES:
        try:
            r = httpx.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={"query": q, "location": f"{lat},{lng}",
                        "radius": int(radius_mi * 1609.34), "key": key},
                timeout=15,
            )
            r.raise_for_status()
            results.extend(r.json().get("results") or [])
        except Exception:  # noqa: BLE001
            continue
    log_agent("vance", "gmaps_search", payload={"loc": [lat, lng]}, result=str(len(results)))
    return results

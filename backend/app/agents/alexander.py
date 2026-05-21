"""Alexander Wright — VP Market Intelligence (IEBC Step 55).
Queries the US DOT open data API (data.transportation.gov) for
carrier/transport market data, surfaces competitive intelligence,
and identifies lane/capacity opportunities for 3 Lakes Logistics.

API endpoint: https://data.transportation.gov/api/v3/views/az4n-8mr2/query.json
Set DOT_API_KEY in environment (Socrata app token for higher rate limits).
Daily task to be refined once dataset structure is confirmed.
"""
from __future__ import annotations

import urllib.request
import urllib.parse
import json
from typing import Any

from ..logging_service import log_agent
from ..settings import get_settings

DOT_BASE = "https://data.transportation.gov/resource/az4n-8mr2.json"


def _fetch_dot(limit: int = 100, offset: int = 0, where: str | None = None) -> list[dict]:
    """Fetch records from the DOT dataset via Socrata REST API."""
    settings = get_settings()
    params: dict[str, Any] = {"$limit": limit, "$offset": offset}
    if where:
        params["$where"] = where

    url = DOT_BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)

    # Socrata app token — raises rate limit from 1 req/s to 1000 req/s
    if settings.dot_api_key:
        req.add_header("X-App-Token", settings.dot_api_key)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        raise RuntimeError(f"DOT API fetch failed: {exc}") from exc


def analyze_market(limit: int = 100) -> dict[str, Any]:
    """Pull DOT dataset and extract market intelligence signals."""
    raw = _fetch_dot(limit=limit)

    if not raw:
        return {"records_fetched": 0, "note": "No data returned from DOT API — verify dataset ID and API key"}

    # Introspect available columns from first record
    sample_keys = list(raw[0].keys()) if raw else []

    # Generic aggregation pass — works regardless of exact column names
    # The actual field analysis will be refined once dataset structure confirmed
    record_count = len(raw)

    # Attempt to find state/region distribution
    state_field = next((k for k in sample_keys if "state" in k.lower()), None)
    state_dist: dict[str, int] = {}
    if state_field:
        for row in raw:
            val = str(row.get(state_field) or "unknown").strip().upper()
            state_dist[val] = state_dist.get(val, 0) + 1
        top_states = sorted(state_dist.items(), key=lambda x: x[1], reverse=True)[:10]
    else:
        top_states = []

    # Attempt carrier/company column
    carrier_field = next((k for k in sample_keys if any(t in k.lower() for t in ["carrier", "company", "name", "entity"])), None)

    # Build intelligence output
    return {
        "records_fetched": record_count,
        "dataset_columns": sample_keys,
        "sample_record": raw[0] if raw else {},
        "geographic_distribution": dict(top_states),
        "top_state_by_volume": top_states[0][0] if top_states else None,
        "carrier_field_detected": carrier_field,
        "intelligence_note": (
            "Dataset structure mapped. Refine daily_task() with specific field "
            "names from dataset_columns to extract targeted market insights."
        ),
    }


def run(payload: dict[str, Any]) -> dict[str, Any]:
    limit = int(payload.get("limit", 100))
    try:
        result = analyze_market(limit=limit)
        log_agent(
            "alexander", "market_intel",
            payload={"limit": limit},
            result=f"records={result.get('records_fetched', 0)}"
        )
        return {"agent": "alexander", **result}
    except RuntimeError as exc:
        log_agent("alexander", "market_intel", payload={}, result=f"ERROR: {exc}")
        return {"agent": "alexander", "error": str(exc), "records_fetched": 0}

"""Load board prospecting helpers — carrier directory harvest for lead pool.

For active load search use loadboard_clients.search_all() via Sonny.
This module handles carrier directory scraping for the prospecting pipeline.
"""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent
from .loadboard_clients import SearchParams, search_all


def search_loads_for_truck(
    origin_state: str,
    trailer_type: str,
    max_weight_lbs: int = 45000,
    max_deadhead_mi: int = 150,
) -> list[dict[str, Any]]:
    """Fan out to all 15 load board sources and return standardized load dicts."""
    params = SearchParams(
        origin_state=origin_state,
        trailer_type=trailer_type,
        max_weight_lbs=max_weight_lbs,
        max_deadhead_mi=max_deadhead_mi,
    )
    results = search_all(params)
    log_agent("sonny", "loadboard_search",
              payload={"origin": origin_state, "trailer": trailer_type},
              result=f"{len(results)} loads")
    return [r.__dict__ for r in results]


def scrape_dat_directory(state: str) -> list[dict[str, Any]]:
    """DAT carrier directory — used for prospect pool, not load search."""
    log_agent("vance", "dat_scrape", payload={"state": state}, result="stub")
    return []


def scrape_truckstop_directory(state: str) -> list[dict[str, Any]]:
    """Truckstop carrier directory — used for prospect pool."""
    log_agent("vance", "truckstop_scrape", payload={"state": state}, result="stub")
    return []

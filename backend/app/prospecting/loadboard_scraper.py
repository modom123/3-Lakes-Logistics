"""Load board data access (Stage 5).

- `fetch_recent()`: normalized open loads across configured sources.
- `scrape_dat_directory` / `scrape_truckstop_directory`: carrier
  directory scrape for prospect pool.

Real scrapers respect robots.txt and rate-limit at 1 req / 2 s. Until
source credentials are provisioned, `fetch_recent` returns rows from the
Supabase `loads` table (populated by scheduled scraper jobs) instead of
hitting external APIs inline.
"""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent


def fetch_recent(limit: int = 200) -> list[dict[str, Any]]:
    """Return the most recently ingested open loads (cross-source)."""
    try:
        from ..supabase_client import get_supabase
        rows = (
            get_supabase().table("loads")
            .select("source,ref,origin,destination,miles,rate_total,rate_per_mile,"
                    "trailer_type,weight_lbs,deadhead_mi,duration_h,created_at")
            .eq("status", "open")
            .order("created_at", desc=True).limit(limit).execute()
        ).data or []
        return rows
    except Exception as exc:  # noqa: BLE001
        log_agent("sonny", "loads_fetch_failed", error=str(exc))
        return []


def scrape_dat_directory(state: str) -> list[dict[str, Any]]:
    log_agent("vance", "dat_scrape", payload={"state": state}, result="stub")
    return []


def scrape_truckstop_directory(state: str) -> list[dict[str, Any]]:
    log_agent("vance", "truckstop_scrape", payload={"state": state}, result="stub")
    return []

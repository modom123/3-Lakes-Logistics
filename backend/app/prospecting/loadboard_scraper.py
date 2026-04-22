"""Step 43: DAT/Truckstop directory scraper.

Public carrier directory listings are harvested to pad the prospect pool.
Respect robots.txt — rate-limit at 1 req / 2 sec.
"""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent


def scrape_dat_directory(state: str) -> list[dict[str, Any]]:
    """Stub. Real version uses BeautifulSoup against public DAT directory."""
    log_agent("vance", "dat_scrape", payload={"state": state}, result="stub")
    return []


def scrape_truckstop_directory(state: str) -> list[dict[str, Any]]:
    log_agent("vance", "truckstop_scrape", payload={"state": state}, result="stub")
    return []

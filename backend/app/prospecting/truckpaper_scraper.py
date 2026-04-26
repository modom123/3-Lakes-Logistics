"""Step 57: TruckPaper / CommercialTruckTrader scraper.

Searches equipment-for-sale listings → pulls the seller's phone →
cross-refs DOT registration → new prospect.
"""
from __future__ import annotations

import re
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup

from ..logging_service import log_agent
from ..supabase_client import get_supabase

_BASE = "https://www.truckpaper.com/listings/trucks/for-sale/list/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; 3LakesLogisticsBot/1.0; "
        "+https://3lakeslogistics.com)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_EQUIPMENT_MAP = {
    "dry_van":   "Dry Van",
    "reefer":    "Refrigerated",
    "flatbed":   "Flatbed",
    "tanker":    "Tanker",
    "dump":      "Dump",
    "box_truck": "Box Truck",
}


def _clean_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    return None


def _parse_listings(html: str, state: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, Any]] = []

    for card in soup.select(".listing-card, .result-item, article.listing"):
        try:
            title_el = card.select_one(".listing-title, h2.title, .item-title")
            title = title_el.get_text(strip=True) if title_el else ""

            seller_el = card.select_one(".dealer-name, .seller-name, .company-name")
            company = seller_el.get_text(strip=True) if seller_el else ""

            phone_el = card.select_one(".phone, .dealer-phone, [href^='tel:']")
            phone_raw = ""
            if phone_el:
                phone_raw = (
                    phone_el.get("href", "").replace("tel:", "")
                    or phone_el.get_text(strip=True)
                )

            price_el = card.select_one(".price, .listing-price")
            price = price_el.get_text(strip=True) if price_el else ""

            location_el = card.select_one(".location, .city-state")
            location = location_el.get_text(strip=True) if location_el else state

            if not (company or phone_raw):
                continue

            results.append({
                "source":       "truckpaper",
                "company_name": company or title,
                "phone":        _clean_phone(phone_raw),
                "address":      location,
                "home_state":   state,
                "equipment_types": [title],
                "raw_price":    price,
                "stage":        "new",
            })
        except Exception:  # noqa: BLE001
            continue

    return results


def scrape_truckpaper(state: str, equipment: str = "dry_van") -> list[dict[str, Any]]:
    """Scrape TruckPaper listings for a given state and equipment type.

    Returns a list of raw lead dicts suitable for deduplication + scoring.
    Returns an empty list on any network/parse failure rather than raising.
    """
    equip_label = _EQUIPMENT_MAP.get(equipment, "")
    params: dict[str, Any] = {"State": state.upper(), "CtgryId": 2}
    if equip_label:
        params["Keyword"] = equip_label

    try:
        with httpx.Client(headers=_HEADERS, timeout=15, follow_redirects=True) as client:
            r = client.get(_BASE, params=params)
            r.raise_for_status()
            raw_leads = _parse_listings(r.text, state)
    except Exception as exc:  # noqa: BLE001
        log_agent("scout", "truckpaper_scrape_error",
                  payload={"state": state, "equipment": equipment, "error": str(exc)})
        return []

    log_agent("scout", "truckpaper_scraped",
              payload={"state": state, "equipment": equipment, "found": len(raw_leads)})
    return raw_leads


def ingest(states: list[str] | None = None,
           equipment: str = "dry_van") -> dict[str, Any]:
    """Scrape TruckPaper for multiple states, deduplicate, score, and upsert leads."""
    if states is None:
        states = ["IL", "TX", "OH", "GA", "TN", "FL", "CA", "NC", "PA", "MO"]

    from .dedupe import is_duplicate
    from .scoring import score_lead

    sb = get_supabase()
    inserted = skipped = errors = 0

    for state in states:
        leads = scrape_truckpaper(state, equipment)
        for lead in leads:
            try:
                if is_duplicate(lead.get("dot_number"), lead.get("mc_number")):
                    skipped += 1
                    continue
                lead["score"] = score_lead(lead)
                sb.table("leads").insert(lead).execute()
                inserted += 1
            except Exception:  # noqa: BLE001
                errors += 1
        time.sleep(2)  # polite crawl delay

    return {
        "states_scraped": len(states),
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
    }

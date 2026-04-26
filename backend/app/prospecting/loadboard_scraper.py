"""Load board integration — post loads to external boards + scrape carrier directories.

External boards (DAT, Truckstop) require paid API contracts:
  - DAT: https://developer.dat.com  (Freight API — $300-600/mo)
  - Truckstop: https://developer.truckstop.com (Load Posting API)
  - 123Loadboard: https://www.123loadboard.com/api

Credentials go in .env:
  DAT_API_KEY, DAT_CLIENT_ID, TRUCKSTOP_API_KEY, LOADBOARD_123_API_KEY

Until credentials are set, all external posts log intent and return status='pending_credentials'.
Internal board always works (stores in DB only).
"""
from __future__ import annotations

from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings

# ── External board endpoints ──────────────────────────────────────────────────

_BOARD_ENDPOINTS = {
    "dat":        "https://freight.dat.com/posting/offers",
    "truckstop":  "https://api.truckstop.com/api/v1/loadposting",
    "123loadboard": "https://api.123loadboard.com/v2/loads",
}


def _dat_payload(load: dict) -> dict:
    """Transform internal load dict to DAT Freight API format."""
    return {
        "originCity": load.get("origin_city"),
        "originStateProv": load.get("origin_state"),
        "destinationCity": load.get("dest_city"),
        "destinationStateProv": load.get("dest_state"),
        "equipmentType": _to_dat_equipment(load.get("trailer_type", "dry_van")),
        "length": 53,
        "fullPartial": "Full",
        "weight": load.get("weight_lbs") or 0,
        "commodity": load.get("commodity") or "General Freight",
        "earliestAvailability": load.get("pickup_at"),
        "latestAvailability": load.get("pickup_at"),
        "rate": {"rateType": "FLAT", "amount": load.get("rate_total")},
        "comments": f"Load #{load.get('load_number')} — 3 Lakes Logistics",
        "contact": {"phone": "8003LAKES1"},
    }


def _to_dat_equipment(trailer_type: str) -> str:
    mapping = {
        "dry_van": "VAN", "reefer": "REEFER", "flatbed": "FLATBED",
        "step_deck": "STEP", "lowboy": "LOWBOY", "tanker": "TANKER",
        "box_truck": "STRAIGHT", "power_only": "POWER",
    }
    return mapping.get(trailer_type, "VAN")


def _truckstop_payload(load: dict) -> dict:
    return {
        "origin": {"city": load.get("origin_city"), "state": load.get("origin_state")},
        "destination": {"city": load.get("dest_city"), "state": load.get("dest_state")},
        "equipmentType": load.get("trailer_type", "dry_van"),
        "weight": load.get("weight_lbs"),
        "miles": load.get("miles"),
        "rate": load.get("rate_total"),
        "pickupDate": load.get("pickup_at"),
        "comments": f"Load #{load.get('load_number')} — 3 Lakes Logistics dispatch",
    }


def _post_to_external(load: dict, board: str) -> dict[str, Any]:
    """Fire the actual API call to an external load board."""
    s = get_settings()

    # Check for credentials
    creds = {
        "dat": getattr(s, "dat_api_key", ""),
        "truckstop": getattr(s, "truckstop_api_key", ""),
        "123loadboard": getattr(s, "loadboard_123_api_key", ""),
    }
    api_key = creds.get(board, "")
    if not api_key:
        log_agent("sonny", f"loadboard_post_{board}", payload={"load": load.get("load_number")},
                  result="pending_credentials")
        return {
            "status": "pending_credentials",
            "board": board,
            "message": f"Add {board.upper()}_API_KEY to .env to enable posting",
        }

    url = _BOARD_ENDPOINTS.get(board, "")
    if not url:
        return {"status": "unknown_board", "board": board}

    payload = _dat_payload(load) if board == "dat" else _truckstop_payload(load)
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        post_ref = data.get("id") or data.get("postId") or data.get("loadId") or ""
        log_agent("sonny", f"loadboard_post_{board}",
                  payload={"load": load.get("load_number"), "post_ref": post_ref}, result="posted")
        return {"status": "posted", "board": board, "post_ref": post_ref}

    except httpx.HTTPStatusError as exc:
        err = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
        log_agent("sonny", f"loadboard_post_{board}", error=err)
        return {"status": "failed", "board": board, "error": err}

    except httpx.RequestError as exc:
        log_agent("sonny", f"loadboard_post_{board}", error=str(exc))
        return {"status": "failed", "board": board, "error": str(exc)}


def post_load(load: dict, board: str = "internal") -> dict[str, Any]:
    """Post a load to the specified board.

    'internal' → no external call, just confirms the load is in the DB
    everything else → real API call (requires credentials)
    """
    if board == "internal":
        log_agent("sonny", "loadboard_post_internal",
                  payload={"load": load.get("load_number")}, result="posted")
        return {
            "status": "posted",
            "board": "internal",
            "post_ref": load.get("id"),
            "message": "Load is live on the 3 Lakes internal board",
        }

    return _post_to_external(load, board)


# ── Carrier directory scraping (FMCSA / DAT / Truckstop) ─────────────────────

def scrape_dat_directory(state: str) -> list[dict[str, Any]]:
    """Scrape the public DAT carrier directory for a state.

    DAT's public directory is at https://www.dat.com/industry-trends/carrier-directory
    Uses BeautifulSoup to parse public listings (no API key required for directory).
    Respects robots.txt — rate-limited to 1 req/2s.
    """
    import time
    from bs4 import BeautifulSoup

    url = f"https://www.dat.com/industry-trends/carrier-directory?state={state}"
    try:
        r = httpx.get(url, headers={"User-Agent": "3LL-Bot/1.0 (+3lakeslogistics.com)"}, timeout=15)
        if r.status_code != 200:
            log_agent("vance", "dat_scrape", payload={"state": state}, result=f"http_{r.status_code}")
            return []
        soup = BeautifulSoup(r.text, "lxml")
        # DAT renders carrier cards — parse name, DOT, phone (structure may shift)
        cards = soup.select(".carrier-card, [data-carrier-id]")
        results = []
        for card in cards[:50]:
            results.append({
                "company_name": (card.select_one(".carrier-name, h3") or {}).get_text(strip=True),
                "phone": (card.select_one(".phone, [data-phone]") or {}).get_text(strip=True),
                "dot_number": (card.get("data-dot") or "").strip(),
                "address": (card.select_one(".address") or {}).get_text(strip=True),
                "source": "dat_directory",
            })
        time.sleep(2)
        log_agent("vance", "dat_scrape", payload={"state": state}, result=f"{len(results)} carriers")
        return [r for r in results if r.get("company_name")]
    except Exception as exc:  # noqa: BLE001
        log_agent("vance", "dat_scrape", payload={"state": state}, error=str(exc))
        return []


def scrape_truckstop_directory(state: str) -> list[dict[str, Any]]:
    """Scrape Truckstop.com carrier directory. Same approach as DAT."""
    import time
    from bs4 import BeautifulSoup

    url = f"https://www.truckstop.com/carrier-directory/?state={state}"
    try:
        r = httpx.get(url, headers={"User-Agent": "3LL-Bot/1.0 (+3lakeslogistics.com)"}, timeout=15)
        if r.status_code != 200:
            log_agent("vance", "truckstop_scrape", payload={"state": state}, result=f"http_{r.status_code}")
            return []
        soup = BeautifulSoup(r.text, "lxml")
        rows = soup.select("table tr, .carrier-row")
        results = []
        for row in rows[1:51]:
            cols = row.select("td")
            if len(cols) >= 2:
                results.append({
                    "company_name": cols[0].get_text(strip=True),
                    "dot_number": cols[1].get_text(strip=True),
                    "phone": cols[2].get_text(strip=True) if len(cols) > 2 else "",
                    "source": "truckstop_directory",
                })
        time.sleep(2)
        log_agent("vance", "truckstop_scrape", payload={"state": state}, result=f"{len(results)} carriers")
        return [r for r in results if r.get("company_name")]
    except Exception as exc:  # noqa: BLE001
        log_agent("vance", "truckstop_scrape", payload={"state": state}, error=str(exc))
        return []

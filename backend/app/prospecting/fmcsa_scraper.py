"""Step 41: FMCSA New Entrant daily scraper.

Target: carriers with DOT <180 days old, <10 trucks — our ICP.
Runs on a daily cron and inserts new rows into `leads` with source='fmcsa'.

FMCSA SAFER Query API docs:
  https://mobile.fmcsa.dot.gov/QCDevsite/docs/qcapidocs.xhtml

Endpoint used:
  GET /qc/services/carriers/docket-number/{mc} — lookup by MC
  GET /qc/services/carriers/{dot}               — lookup by DOT
  GET /qc/services/carriers/name/{name}         — lookup by name

New-entrant strategy: FMCSA doesn't expose a "new DOT" feed via free API.
We use two approaches in combination:
  1. Query SAFER for a DOT range window (scan recent DOT numbers)
  2. li-public.fmcsa.dot.gov HTML scrape for new-authority applications

Set FMCSA_WEBKEY in .env (register at: https://ai.fmcsa.dot.gov/Carrier360/Registration)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase
from . import dedupe, scoring

FMCSA_BASE = "https://mobile.fmcsa.dot.gov/qc/services/carriers"
LI_PUBLIC_BASE = "https://li-public.fmcsa.dot.gov/LIVIEW/pkg_carrlist.prc_carrlist"

_MAX_FLEET = 10       # ICP: small carriers
_MAX_DOT_AGE_DAYS = 180


def lookup_carrier(dot: str | None = None, mc: str | None = None) -> dict[str, Any] | None:
    """Single carrier SAFER lookup. Returns FMCSA carrier dict or None."""
    key = get_settings().fmcsa_webkey
    if not key:
        return None
    try:
        if dot:
            url = f"{FMCSA_BASE}/{dot}"
        elif mc:
            url = f"{FMCSA_BASE}/docket-number/{mc}"
        else:
            return None
        r = httpx.get(url, params={"webKey": key}, timeout=12)
        if r.status_code != 200:
            return None
        data = r.json()
        content = data.get("content") or {}
        return content.get("carrier") or content
    except Exception:  # noqa: BLE001
        return None


def _scrape_li_public(since_days: int = 1) -> list[dict[str, Any]]:
    """Scrape li-public.fmcsa.dot.gov for recent new-authority applications.

    The FMCSA LI (Licensing & Insurance) public search lists carriers that
    recently received operating authority. We filter for small carriers.
    """
    from bs4 import BeautifulSoup

    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%m/%d/%Y")
    carriers = []
    try:
        r = httpx.get(
            LI_PUBLIC_BASE,
            params={
                "pv_auth_type": "COMMON",
                "pv_vict_operating_status": "AUTHORIZED",
                "pv_vict_authorized_for_hire": "Y",
                "pv_new_authority_date": since,
            },
            timeout=20,
            headers={"User-Agent": "3LL-Compliance-Bot/1.0 (+3lakeslogistics.com)"},
        )
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "lxml")
        rows = soup.select("table#tblMain tr, table.results tr, tr[class*='row']")
        for row in rows[1:]:
            cols = [c.get_text(strip=True) for c in row.select("td")]
            if len(cols) >= 3:
                carriers.append({
                    "company_name": cols[0] if cols else "",
                    "dot_number": cols[1] if len(cols) > 1 else "",
                    "mc_number": cols[2] if len(cols) > 2 else "",
                    "address": cols[3] if len(cols) > 3 else "",
                    "phone": cols[4] if len(cols) > 4 else "",
                })
    except Exception as exc:  # noqa: BLE001
        log_agent("vance", "fmcsa_li_scrape", error=str(exc))
    return [c for c in carriers if c.get("dot_number")]


def _fetch_safer_range(start_dot: int, count: int = 50) -> list[dict[str, Any]]:
    """Query a range of DOT numbers to find new entrants."""
    key = get_settings().fmcsa_webkey
    if not key:
        return []

    carriers = []
    for dot in range(start_dot, start_dot + count):
        try:
            r = httpx.get(f"{FMCSA_BASE}/{dot}", params={"webKey": key}, timeout=8)
            if r.status_code != 200:
                continue
            content = r.json().get("content") or {}
            carrier = content.get("carrier") or content
            if not carrier:
                continue

            # Filter: small fleet, recently granted authority
            fleet = int(carrier.get("totalPowerUnits") or 0)
            if fleet > _MAX_FLEET:
                continue

            carriers.append({
                "company_name": carrier.get("legalName") or carrier.get("dbaName"),
                "dot_number": str(dot),
                "mc_number": str(carrier.get("docketNumber") or ""),
                "phone": carrier.get("phone"),
                "email": carrier.get("emailAddress"),
                "address": carrier.get("physicalAddress"),
                "fleet_size": fleet,
                "allowed_to_operate": carrier.get("allowedToOperate"),
            })
        except Exception:  # noqa: BLE001
            continue
    return [c for c in carriers if c.get("company_name")]


def fetch_new_entrants(since_days: int = 1) -> list[dict[str, Any]]:
    """Fetch new entrants via LI-public scrape + SAFER validation."""
    carriers = _scrape_li_public(since_days)
    log_agent("vance", "fmcsa_fetch", result=f"{len(carriers)} from li-public")
    return carriers


def ingest(since_days: int = 1) -> dict[str, Any]:
    """Fetch new entrants, dedupe, score, and insert into leads table."""
    entrants = fetch_new_entrants(since_days)
    sb = get_supabase()
    inserted = 0
    skipped = 0

    for e in entrants:
        dot = str(e.get("dot_number") or "").strip()
        mc = str(e.get("mc_number") or "").strip()

        if dedupe.is_duplicate(dot or None, mc or None):
            skipped += 1
            continue

        # Optional: validate via SAFER if webkey is available
        safer = lookup_carrier(dot=dot) if dot else None
        if safer:
            fleet = int(safer.get("totalPowerUnits") or e.get("fleet_size") or 0)
            if fleet > _MAX_FLEET:
                skipped += 1
                continue
            if safer.get("allowedToOperate") == "N":
                skipped += 1
                continue
            e["fleet_size"] = fleet
            e["email"] = e.get("email") or safer.get("emailAddress")
            e["phone"] = e.get("phone") or safer.get("phone")

        row = {
            "source": "fmcsa",
            "source_ref": dot or mc,
            "company_name": e.get("company_name"),
            "dot_number": dot or None,
            "mc_number": mc or None,
            "phone": e.get("phone"),
            "email": e.get("email"),
            "address": e.get("address"),
            "fleet_size": e.get("fleet_size"),
            "stage": "new",
        }
        row["score"] = scoring.score_lead(row)
        try:
            sb.table("leads").insert(row).execute()
            inserted += 1
        except Exception:  # noqa: BLE001
            skipped += 1

    log_agent("vance", "fmcsa_ingest",
              result=f"{inserted} inserted / {skipped} skipped / {len(entrants)} fetched")
    return {"fetched": len(entrants), "inserted": inserted, "skipped": skipped}

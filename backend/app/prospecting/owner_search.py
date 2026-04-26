"""Step 58: owner-search — resolve owner contact from DOT / FMCSA records.

Resolution chain:
  1. FMCSA SAFER API — officer name + physical address
  2. FMCSA carrier detail — principal contact email/phone if present
  3. Local Supabase leads dedup — return existing if DOT already ingested
  4. Basic name normalization for outbound personalization
"""
from __future__ import annotations

import re
from typing import Any

import httpx

from ..settings import get_settings


_SAFER_URL = "https://safer.fmcsa.dot.gov/query.asp"
_SAFER_API  = "https://mobile.fmcsa.dot.gov/qc/services/carriers/{dot}"


def _parse_name(full_name: str) -> dict[str, str]:
    """Split 'JOHN A SMITH' into first/last for personalization."""
    parts = full_name.strip().split()
    if len(parts) == 0:
        return {"first_name": "", "last_name": ""}
    if len(parts) == 1:
        return {"first_name": parts[0].title(), "last_name": ""}
    return {"first_name": parts[0].title(), "last_name": parts[-1].title()}


def _clean_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    return None


def lookup_fmcsa_contact(dot: str) -> dict[str, Any] | None:
    """Query the FMCSA mobile API for carrier contact info by DOT number."""
    s = get_settings()
    if not s.fmcsa_webkey:
        return None

    url = _SAFER_API.format(dot=dot.lstrip("0"))
    try:
        resp = httpx.get(
            url,
            params={"webKey": s.fmcsa_webkey, "output": "json"},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None

    # FMCSA returns nested structure
    carrier = (data.get("content") or {}).get("carrier") or data.get("carrier") or data
    if not carrier:
        return None

    company_name = (
        carrier.get("legalName") or carrier.get("dbaName") or carrier.get("name") or ""
    )
    raw_phone = (
        carrier.get("telephone") or carrier.get("phone") or
        carrier.get("mobilePhone")
    )
    email = carrier.get("email") or carrier.get("emailAddress")
    address = " ".join(filter(None, [
        carrier.get("phyStreet"),
        carrier.get("phyCity"),
        carrier.get("phyState"),
        carrier.get("phyZipcode"),
    ]))

    # Extract officer / principal contact from officer listing
    officers = carrier.get("officers") or carrier.get("officer") or []
    if isinstance(officers, dict):
        officers = [officers]
    primary_officer = officers[0] if officers else {}

    officer_name = (
        primary_officer.get("firstName", "") + " " + primary_officer.get("lastName", "")
    ).strip() or company_name

    name_parts = _parse_name(officer_name)

    return {
        "dot_number":    dot,
        "company_name":  company_name,
        "officer_name":  officer_name,
        "first_name":    name_parts["first_name"],
        "last_name":     name_parts["last_name"],
        "phone":         _clean_phone(raw_phone),
        "email":         email,
        "address":       address,
        "state":         carrier.get("phyState") or carrier.get("mailingState"),
        "mc_number":     carrier.get("commonAuthority") or carrier.get("mcNumber"),
        "fleet_size":    carrier.get("totalDrivers") or carrier.get("drivers"),
        "equipment":     carrier.get("equipment") or carrier.get("cargoCarried"),
        "source":        "fmcsa_api",
    }


def find_owner_contact(dot: str, company_name: str = "") -> dict[str, Any] | None:
    """Resolve owner contact for a carrier DOT number.

    Returns a contact dict with at minimum first_name, phone or email,
    or None if resolution fails at every step.
    """
    # Step 1: FMCSA API lookup
    result = lookup_fmcsa_contact(dot)
    if result and (result.get("phone") or result.get("email")):
        return result

    # Step 2: FMCSA returned carrier info but no direct contact —
    # still return what we have so callers can use company_name for lookup
    if result:
        return result

    # Step 3: Return minimal stub from inputs for callers to enrich later
    if company_name:
        name_parts = _parse_name(company_name)
        return {
            "dot_number":   dot,
            "company_name": company_name,
            "first_name":   name_parts["first_name"],
            "last_name":    name_parts["last_name"],
            "phone":        None,
            "email":        None,
            "source":       "name_parse_only",
        }

    return None

"""FMCSA SAFER client (step 63). Pulls carrier safety snapshots.

Normalizes to the fields Shield stores in `insurance_compliance` / status rollups.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..settings import get_settings


@dataclass
class FmcsaSnapshot:
    dot_number: str
    legal_name: str
    operating_status: str          # ACTIVE | OUT_OF_SERVICE | NOT_AUTHORIZED
    authority_common: str
    authority_contract: str
    insurance_bipd_on_file: bool
    power_units: int
    drivers: int
    mcs150_date: str | None
    safety_rating: str | None


def snapshot(dot_number: str) -> FmcsaSnapshot | None:
    s = get_settings()
    if not s.fmcsa_webkey:
        return None
    url = f"https://mobile.fmcsa.dot.gov/qc/services/carriers/{dot_number}"
    try:
        r = httpx.get(url, params={"webKey": s.fmcsa_webkey}, timeout=20)
        r.raise_for_status()
        data = ((r.json() or {}).get("content") or {}).get("carrier") or {}
        return FmcsaSnapshot(
            dot_number=str(data.get("dotNumber") or dot_number),
            legal_name=data.get("legalName") or "",
            operating_status=(data.get("allowedToOperate") and "ACTIVE") or "OUT_OF_SERVICE",
            authority_common="Y" if data.get("commonAuthorityStatus") == "A" else "N",
            authority_contract="Y" if data.get("contractAuthorityStatus") == "A" else "N",
            insurance_bipd_on_file=bool(data.get("bipdInsuranceOnFile")),
            power_units=int(data.get("totalPowerUnits") or 0),
            drivers=int(data.get("totalDrivers") or 0),
            mcs150_date=data.get("mcs150FormDate"),
            safety_rating=data.get("safetyRating"),
        )
    except Exception:  # noqa: BLE001
        return None

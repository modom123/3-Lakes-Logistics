"""Shield — Steps 25-26. FMCSA SAFER verification + safety-light scoring."""
from __future__ import annotations

from typing import Any, Literal

import httpx

from ..logging_service import log_agent
from ..settings import get_settings
from ..supabase_client import get_supabase

SafetyLight = Literal["green", "yellow", "red"]

FMCSA_SAFER_BASE = "https://mobile.fmcsa.dot.gov/qc/services/carriers"


def fetch_safer(dot: str | None) -> dict[str, Any] | None:
    """Step 25: pull SAFER/CSA snapshot for a DOT number."""
    if not dot:
        return None
    key = get_settings().fmcsa_webkey
    if not key:
        return {"stub": True, "dot": dot, "note": "FMCSA_WEBKEY missing"}
    try:
        r = httpx.get(f"{FMCSA_SAFER_BASE}/{dot}", params={"webKey": key}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "dot": dot}


def score(safer: dict[str, Any] | None, insurance_expiry: str | None = None) -> SafetyLight:
    """Step 26: traffic-light from SAFER + insurance.
       green:  allowed=Y, no recent OOS, insurance current
       yellow: insurance within 30 days of expiry or borderline BASIC scores
       red:    allowedToOperate=N, active OOS order, or expired insurance
    """
    if not safer or safer.get("error"):
        return "yellow"
    content = safer.get("content", {}) if isinstance(safer, dict) else {}
    carrier = content.get("carrier", {}) if isinstance(content, dict) else {}
    if carrier.get("allowedToOperate") == "N":
        return "red"
    if carrier.get("oosDate"):
        return "red"
    # TODO: integrate CSA BASIC thresholds + insurance expiry
    return "green"


def enqueue_safety_check(carrier_id: str, dot: str | None, mc: str | None) -> None:
    """Called from the intake route — fire-and-forget."""
    log_agent("shield", "enqueue", carrier_id=carrier_id, payload={"dot": dot, "mc": mc})
    safer = fetch_safer(dot)
    light = score(safer)
    try:
        get_supabase().table("insurance_compliance").update(
            {"safety_light": light, "last_checked_at": "now()"}
        ).eq("carrier_id", carrier_id).execute()
    except Exception as e:  # noqa: BLE001
        log_agent("shield", "update_light", carrier_id=carrier_id, error=str(e))


def run(payload: dict[str, Any]) -> dict[str, Any]:
    dot = payload.get("dot_number")
    safer = fetch_safer(dot)
    light = score(safer)
    log_agent("shield", "run", payload=payload, result=light)
    return {"agent": "shield", "dot": dot, "safety_light": light, "safer": safer}

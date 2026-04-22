"""Audit — Document audits + retention purge (step 67 + step 79)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..logging_service import log_agent
from ..settings import get_settings


def decide_advance(driver_id: str, amount: float, load_rate: float) -> dict[str, Any]:
    approved = amount <= max(load_rate * 0.40, 500.0)
    return {
        "driver_id": driver_id, "amount": amount,
        "approved": approved,
        "reason": "within 40% of rate" if approved else "exceeds 40% cap",
    }


def parse_coi(text: str) -> dict[str, Any]:
    """Extract carrier, policy number, and expiry from raw OCR'd COI text."""
    import re
    low = (text or "").lower()
    carrier = re.search(r"carrier[:\s]+([A-Za-z0-9& ,.-]{3,})", low)
    policy = re.search(r"policy\s*(?:no|number)[:\s#]+([A-Z0-9-]{5,})", text, re.IGNORECASE)
    expiry = re.search(
        r"(?:expir(?:es|y|ation)|until)[:\s]+([01]?\d[/-][0-3]?\d[/-]\d{2,4})",
        text, re.IGNORECASE,
    )
    return {
        "insurance_carrier": (carrier.group(1).title() if carrier else None),
        "policy_number": (policy.group(1) if policy else None),
        "policy_expiry": (expiry.group(1) if expiry else None),
    }


def parse_w9(text: str) -> dict[str, Any]:
    import re
    name = re.search(r"^\s*1\s+(.+)$", text or "", re.MULTILINE)
    ein = re.search(r"\b\d{2}-?\d{7}\b", text or "")
    addr = re.search(r"address[^\n]*\n([^\n]+)", text or "", re.IGNORECASE)
    return {
        "payee_name": (name.group(1).strip() if name else None),
        "ein": (ein.group(0).replace("-", "") if ein else None),
        "address": (addr.group(1).strip() if addr else None),
    }


def retention_purge() -> dict[str, Any]:
    """Step 79 — honor data-retention TTLs."""
    s = get_settings()
    cutoff_leads = (
        datetime.now(timezone.utc) - timedelta(days=s.retention_days_leads)
    ).isoformat()
    cutoff_webhooks = (
        datetime.now(timezone.utc) - timedelta(days=s.retention_days_webhooks)
    ).isoformat()
    purged = {"leads": 0, "webhook_log": 0}
    try:
        from ..supabase_client import get_supabase
        sb = get_supabase()
        r1 = sb.table("leads").delete().lt("last_touch_at", cutoff_leads).in_(
            "stage", ["cold", "lost"]).execute()
        purged["leads"] = len(r1.data or [])
        r2 = sb.table("webhook_log").delete().lt("created_at", cutoff_webhooks).execute()
        purged["webhook_log"] = len(r2.data or [])
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}
    log_agent("audit", "retention_purge", result=str(purged))
    return {"status": "ok", **purged}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    kind = payload.get("kind") or "advance"
    if kind == "retention_purge":
        return {"agent": "audit", **retention_purge()}
    if kind == "parse_coi":
        return {"agent": "audit", "status": "ok", **parse_coi(payload.get("text") or "")}
    if kind == "parse_w9":
        return {"agent": "audit", "status": "ok", **parse_w9(payload.get("text") or "")}
    res = decide_advance(
        payload.get("driver_id", ""),
        float(payload.get("amount") or 0),
        float(payload.get("load_rate") or 0),
    )
    return {"agent": "audit", "status": "ok", **res}

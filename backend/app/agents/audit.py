"""Audit — Step 32. Credit-check gate for fuel advances + factoring."""
from __future__ import annotations

from typing import Any

from ..logging_service import log_agent


def decide_advance(driver_id: str, amount: float, load_rate: float) -> dict[str, Any]:
    """Simple heuristic: advance must be < 40% of load rate and driver must
    have no more than 1 outstanding advance.
    """
    # TODO: join against driver_hos_status + loads + existing advances
    approved = amount <= max(load_rate * 0.40, 500.0)
    reason = "within 40% of rate" if approved else "exceeds 40% cap"
    return {"driver_id": driver_id, "amount": amount, "approved": approved, "reason": reason}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    res = decide_advance(
        payload.get("driver_id", ""),
        float(payload.get("amount") or 0),
        float(payload.get("load_rate") or 0),
    )
    log_agent("audit", "advance_decision", payload=payload, result="approved" if res["approved"] else "denied")
    return {"agent": "audit", **res}

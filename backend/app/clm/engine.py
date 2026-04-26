"""CLM execution engine — links contract events to accounting and GL actions."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from ..supabase_client import get_supabase

log = logging.getLogger("3ll.clm.engine")


def post_contract_event(
    contract_id: UUID,
    event_type: str,
    actor: str,
    payload: dict | None = None,
    notes: str | None = None,
) -> None:
    sb = get_supabase()
    sb.table("contract_events").insert({
        "contract_id": str(contract_id),
        "event_type": event_type,
        "actor": actor,
        "payload": payload or {},
        "notes": notes,
    }).execute()


def update_milestone(contract_id: UUID, milestone_pct: int, notes: str | None = None) -> dict:
    """Update contract completion % and trigger GL/ledger actions at key thresholds."""
    sb = get_supabase()

    update_data: dict = {
        "milestone_pct": milestone_pct,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if milestone_pct >= 100:
        update_data["status"] = "executed"

    result = sb.table("contracts").update(update_data).eq("id", str(contract_id)).execute()
    post_contract_event(contract_id, "milestone", "clm.engine", {"milestone_pct": milestone_pct}, notes)

    # Write atomic ledger events at business-significant milestones
    if milestone_pct in (50, 90, 100):
        _write_ledger_milestone(contract_id, milestone_pct)

    log.info("contract=%s milestone=%d%%", contract_id, milestone_pct)
    return result.data[0] if result.data else {}


def trigger_invoice(contract_id: UUID) -> dict:
    """Recognize revenue for a contract and write to the atomic ledger."""
    sb = get_supabase()

    result = sb.table("contracts").select("*").eq("id", str(contract_id)).single().execute()
    contract = result.data
    if not contract:
        raise ValueError(f"Contract {contract_id} not found")

    sb.table("contracts").update({
        "revenue_recognized": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", str(contract_id)).execute()

    sb.table("atomic_ledger").insert({
        "event_type": "contract.revenue_recognized",
        "event_source": "clm.engine",
        "logistics_payload": {
            "contract_id": str(contract_id),
            "contract_type": contract.get("contract_type"),
            "origin_city": contract.get("origin_city"),
            "destination_city": contract.get("destination_city"),
        },
        "financial_payload": {
            "rate_total": contract.get("rate_total"),
            "rate_per_mile": contract.get("rate_per_mile"),
            "payment_terms": contract.get("payment_terms"),
            "counterparty": contract.get("counterparty_name"),
        },
        "compliance_payload": {
            "gl_posted": contract.get("gl_posted", False),
            "actor": "clm.engine",
        },
    }).execute()

    post_contract_event(
        contract_id, "invoiced", "clm.engine",
        {"rate_total": contract.get("rate_total")},
    )
    log.info("contract=%s revenue recognized rate=$%s", contract_id, contract.get("rate_total"))
    return contract


def _write_ledger_milestone(contract_id: UUID, milestone_pct: int) -> None:
    sb = get_supabase()
    try:
        sb.table("atomic_ledger").insert({
            "event_type": f"contract.milestone.{milestone_pct}pct",
            "event_source": "clm.engine",
            "logistics_payload": {"contract_id": str(contract_id)},
            "financial_payload": {},
            "compliance_payload": {"milestone_pct": milestone_pct},
        }).execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to write ledger milestone event: %s", exc)

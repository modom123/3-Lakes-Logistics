"""Step executor — runs individual steps and tracks state in Supabase."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from ..supabase_client import get_supabase
from ..logging_service import get_logger
from .registry import STEP_REGISTRY, Step
from ..clm.steps import (
    step_121_email_inbound_parse,
    step_122_doc_classify,
    step_123_extract_variables,
    step_124_digital_twin_create,
    step_125_revenue_leakage_check,
    step_126_counterparty_lookup,
    step_127_duplicate_detect,
    step_128_expiry_schedule,
    step_129_broker_blacklist_check,
    step_130_rate_benchmark,
    step_131_auto_approve,
    step_132_flag_for_review,
    step_133_milestone_10pct,
    step_134_milestone_50pct,
    step_135_milestone_90pct,
    step_136_milestone_100pct,
    step_137_gl_trigger,
    step_138_factoring_eligibility,
    step_139_broker_agreement_link,
    step_140_payment_terms_enforce,
    step_141_dispute_open,
    step_142_dispute_escalate,
    step_143_archive_executed,
    step_144_analytics_update,
    step_145_broker_scorecard,
    step_146_volume_discount_check,
    step_147_auto_renew_agreement,
    step_148_contract_export,
    step_149_compliance_audit,
    step_150_clm_complete,
)

log = get_logger("3ll.execution.executor")

# Maps step number → concrete handler for CLM domain (121-150)
_CLM_HANDLERS: dict[int, object] = {
    121: step_121_email_inbound_parse,
    122: step_122_doc_classify,
    123: step_123_extract_variables,
    124: step_124_digital_twin_create,
    125: step_125_revenue_leakage_check,
    126: step_126_counterparty_lookup,
    127: step_127_duplicate_detect,
    128: step_128_expiry_schedule,
    129: step_129_broker_blacklist_check,
    130: step_130_rate_benchmark,
    131: step_131_auto_approve,
    132: step_132_flag_for_review,
    133: step_133_milestone_10pct,
    134: step_134_milestone_50pct,
    135: step_135_milestone_90pct,
    136: step_136_milestone_100pct,
    137: step_137_gl_trigger,
    138: step_138_factoring_eligibility,
    139: step_139_broker_agreement_link,
    140: step_140_payment_terms_enforce,
    141: step_141_dispute_open,
    142: step_142_dispute_escalate,
    143: step_143_archive_executed,
    144: step_144_analytics_update,
    145: step_145_broker_scorecard,
    146: step_146_volume_discount_check,
    147: step_147_auto_renew_agreement,
    148: step_148_contract_export,
    149: step_149_compliance_audit,
    150: step_150_clm_complete,
}


def run_step(
    step_number: int,
    carrier_id: UUID | None = None,
    contract_id: UUID | None = None,
    input_payload: dict | None = None,
) -> dict:
    """Execute a single step, recording state in Supabase execution_steps."""
    step = STEP_REGISTRY.get(step_number)
    if not step:
        raise ValueError(f"Step {step_number} not found in registry")

    sb = get_supabase()
    record: dict = {
        "step_number": step_number,
        "step_name": step.name,
        "domain": step.domain,
        "status": "running",
        "input_payload": input_payload or {},
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if carrier_id:
        record["carrier_id"] = str(carrier_id)
    if contract_id:
        record["contract_id"] = str(contract_id)

    result = sb.table("execution_steps").insert(record).execute()
    exec_id = result.data[0]["id"]

    t0 = time.monotonic()
    try:
        output = _dispatch(step, carrier_id, contract_id, input_payload or {})
        duration_ms = int((time.monotonic() - t0) * 1000)

        sb.table("execution_steps").update({
            "status": "complete",
            "output_payload": output,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
        }).eq("id", exec_id).execute()

        log.info("step=%d (%s) complete %dms", step_number, step.name, duration_ms)
        return {"exec_id": exec_id, "step": step_number, "status": "complete", "output": output}

    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - t0) * 1000)
        sb.table("execution_steps").update({
            "status": "failed",
            "error_message": str(exc),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": duration_ms,
        }).eq("id", exec_id).execute()

        log.error("step=%d (%s) failed: %s", step_number, step.name, exc)
        return {"exec_id": exec_id, "step": step_number, "status": "failed", "error": str(exc)}


def run_domain(
    domain: str,
    carrier_id: UUID | None = None,
    contract_id: UUID | None = None,
) -> list[dict]:
    """Run all steps in a domain sequentially, stopping on first failure."""
    steps = sorted(
        [s for s in STEP_REGISTRY.values() if s.domain == domain],
        key=lambda s: s.number,
    )
    results: list[dict] = []
    for step in steps:
        r = run_step(step.number, carrier_id, contract_id)
        results.append(r)
        if r["status"] == "failed":
            log.warning("domain=%s halted at step=%d", domain, step.number)
            break
    return results


def _dispatch(
    step: Step,
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Route step execution to a concrete handler when available.

    CLM steps 121-150 are fully implemented in clm.steps.
    All other domains fall back to the metadata stub — concrete handlers
    for those domains are added in subsequent sprint cycles.
    """
    handler = _CLM_HANDLERS.get(step.number)
    if handler is not None:
        return handler(carrier_id, contract_id, payload)  # type: ignore[call-arg]

    # Stub for domains not yet implemented (onboarding, dispatch, transit,
    # settlement, compliance, analytics — handled in future sprints)
    return {
        "step_number": step.number,
        "step_name": step.name,
        "domain": step.domain,
        "description": step.description,
        "carrier_id": str(carrier_id) if carrier_id else None,
        "contract_id": str(contract_id) if contract_id else None,
        "auto_trigger": step.auto_trigger,
        "requires_steps": step.requires_steps,
        "executed": True,
        "stub": True,
    }

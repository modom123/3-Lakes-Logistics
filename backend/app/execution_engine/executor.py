"""Step executor — runs individual steps and tracks state in Supabase."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from ..logging_service import get_logger
from .registry import STEP_REGISTRY, Step
from .handlers import HANDLER_MAP
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
from ..compliance.steps import (
    step_151_daily_sweep,
    step_152_csa_refresh,
    step_153_insurance_30d,
    step_154_insurance_7d,
    step_155_insurance_expired,
    step_156_mc_authority_check,
    step_157_cdl_expiry_check,
    step_158_cdl_expiry_30d,
    step_159_cdl_expiry_7d,
    step_160_drug_test_schedule,
    step_161_accident_flag,
    step_162_oos_rate_check,
    step_163_safety_light_update,
    step_164_red_light_suspend,
    step_165_compliance_email,
    step_166_compliance_sms,
    step_167_hazmat_cert_check,
    step_168_oversize_permit,
    step_169_ifta_compliance,
    step_170_ucr_registration,
    step_171_annual_inspection,
    step_172_dot_audit_prep,
    step_173_eld_mandate_check,
    step_174_cargo_insurance,
    step_175_new_entrant_monitor,
    step_176_driver_mvr_check,
    step_177_lease_agreement,
    step_178_escrow_audit,
    step_179_compliance_score,
    step_180_compliance_complete,
)
from ..analytics.steps import (
    step_181_daily_kpi,
    step_182_fleet_utilization,
    step_183_lane_profitability,
    step_184_broker_performance,
    step_185_driver_ranking,
    step_186_revenue_forecast,
    step_187_fuel_analysis,
    step_188_dead_head_report,
    step_189_detention_report,
    step_190_spot_vs_contract,
    step_191_cash_flow,
    step_192_carrier_ltv,
    step_193_csa_trend,
    step_194_rate_index,
    step_195_equipment_demand,
    step_196_compliance_risk,
    step_197_weekly_report,
    step_198_airtable_sync,
    step_199_sentry_health,
    step_200_analytics_complete,
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

# Maps step number → concrete handler for compliance domain (151-180)
_COMPLIANCE_HANDLERS: dict[int, object] = {
    151: step_151_daily_sweep,
    152: step_152_csa_refresh,
    153: step_153_insurance_30d,
    154: step_154_insurance_7d,
    155: step_155_insurance_expired,
    156: step_156_mc_authority_check,
    157: step_157_cdl_expiry_check,
    158: step_158_cdl_expiry_30d,
    159: step_159_cdl_expiry_7d,
    160: step_160_drug_test_schedule,
    161: step_161_accident_flag,
    162: step_162_oos_rate_check,
    163: step_163_safety_light_update,
    164: step_164_red_light_suspend,
    165: step_165_compliance_email,
    166: step_166_compliance_sms,
    167: step_167_hazmat_cert_check,
    168: step_168_oversize_permit,
    169: step_169_ifta_compliance,
    170: step_170_ucr_registration,
    171: step_171_annual_inspection,
    172: step_172_dot_audit_prep,
    173: step_173_eld_mandate_check,
    174: step_174_cargo_insurance,
    175: step_175_new_entrant_monitor,
    176: step_176_driver_mvr_check,
    177: step_177_lease_agreement,
    178: step_178_escrow_audit,
    179: step_179_compliance_score,
    180: step_180_compliance_complete,
}

# Maps step number → concrete handler for analytics domain (181-200)
_ANALYTICS_HANDLERS: dict[int, object] = {
    181: step_181_daily_kpi,
    182: step_182_fleet_utilization,
    183: step_183_lane_profitability,
    184: step_184_broker_performance,
    185: step_185_driver_ranking,
    186: step_186_revenue_forecast,
    187: step_187_fuel_analysis,
    188: step_188_dead_head_report,
    189: step_189_detention_report,
    190: step_190_spot_vs_contract,
    191: step_191_cash_flow,
    192: step_192_carrier_ltv,
    193: step_193_csa_trend,
    194: step_194_rate_index,
    195: step_195_equipment_demand,
    196: step_196_compliance_risk,
    197: step_197_weekly_report,
    198: step_198_airtable_sync,
    199: step_199_sentry_health,
    200: step_200_analytics_complete,
}


def _sb():
    """Return Supabase client or None if not configured."""
    try:
        from ..supabase_client import get_supabase
        return get_supabase()
    except Exception:  # noqa: BLE001
        return None


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

    exec_id: str | None = None
    sb = _sb()

    if sb:
        try:
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
        except Exception as e:  # noqa: BLE001
            log.warning("execution_steps insert failed (Supabase unavailable?): %s", e)

    t0 = time.monotonic()
    try:
        output = _dispatch(step, carrier_id, contract_id, input_payload or {})
        duration_ms = int((time.monotonic() - t0) * 1000)

        if sb and exec_id:
            try:
                sb.table("execution_steps").update({
                    "status": "complete",
                    "output_payload": output,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": duration_ms,
                }).eq("id", exec_id).execute()
            except Exception as e:  # noqa: BLE001
                log.warning("execution_steps update failed: %s", e)

        log.info("step=%d (%s) complete %dms", step_number, step.name, duration_ms)
        return {"exec_id": exec_id, "step": step_number, "status": "complete", "output": output}

    except Exception as exc:  # noqa: BLE001
        duration_ms = int((time.monotonic() - t0) * 1000)

        if sb and exec_id:
            try:
                sb.table("execution_steps").update({
                    "status": "failed",
                    "error_message": str(exc),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "duration_ms": duration_ms,
                }).eq("id", exec_id).execute()
            except Exception as e:  # noqa: BLE001
                log.warning("execution_steps failure update failed: %s", e)

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
    """Route step to its concrete handler."""
    # Try HANDLER_MAP first (onboarding, dispatch, transit, settlement)
    handler = HANDLER_MAP.get(step.number)
    if handler:
        return handler(carrier_id, contract_id, payload)

    # Then try CLM (121-150), Compliance (151-180), and Analytics (181-200)
    handler = (
        _CLM_HANDLERS.get(step.number)
        or _COMPLIANCE_HANDLERS.get(step.number)
        or _ANALYTICS_HANDLERS.get(step.number)
    )
    if handler is not None:
        return handler(carrier_id, contract_id, payload)  # type: ignore[call-arg]

    # Fallback stub (should not occur for valid step numbers)
    return {
        "step_number": step.number,
        "step_name": step.name,
        "domain": step.domain,
        "description": step.description,
        "carrier_id": str(carrier_id) if carrier_id else None,
        "contract_id": str(contract_id) if contract_id else None,
        "requires_steps": step.requires_steps,
        "executed": True,
        "note": "handler_not_found",
        "stub": True,
    }

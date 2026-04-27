"""Step executor — runs individual steps and tracks state in Supabase."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from ..logging_service import get_logger
from .registry import STEP_REGISTRY, Step
from .handlers import HANDLER_MAP

log = get_logger("3ll.execution.executor")


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
    """Route step to its concrete handler, falling back to a structured stub."""
    handler = HANDLER_MAP.get(step.number)
    if handler:
        return handler(carrier_id, contract_id, payload)
    return {
        "step_number": step.number,
        "step_name": step.name,
        "domain": step.domain,
        "description": step.description,
        "carrier_id": str(carrier_id) if carrier_id else None,
        "contract_id": str(contract_id) if contract_id else None,
        "requires_steps": step.requires_steps,
        "executed": True,
        "note": "handler_not_yet_implemented",
    }

"""Step executor — runs individual steps and tracks state in Supabase."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from ..supabase_client import get_supabase
from ..logging_service import get_logger
from .registry import STEP_REGISTRY, Step

log = get_logger("3ll.execution.executor")


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


# ── Step-to-agent dispatch table ──────────────────────────────────────────────
# Maps step.name prefix → callable(step, carrier_id, contract_id, payload) → dict

def _dispatch(
    step: Step,
    carrier_id: UUID | None,
    contract_id: UUID | None,
    payload: dict,
) -> dict:
    """Route each step to the appropriate agent or service."""
    cid = str(carrier_id) if carrier_id else payload.get("carrier_id", "")
    base = {
        "step_number": step.number,
        "step_name": step.name,
        "domain": step.domain,
        "carrier_id": cid,
        "contract_id": str(contract_id) if contract_id else None,
    }

    # ── Onboarding ─────────────────────────────────────────────────────────────
    if step.name == "nova.welcome_email":
        from ..agents.nova import send_welcome
        return {**base, **send_welcome({**payload, "carrier_id": cid})}

    if step.name == "signal.notify_commander":
        from ..agents.signal import send_emergency
        return {**base, **send_emergency({**payload, "carrier_id": cid,
                "incident_type": "New carrier activation"})}

    if step.name in ("fmcsa.lookup", "shield.safety_light", "shield.pre_dispatch_safety"):
        from ..agents.shield import fetch_safer, score, enqueue_safety_check
        dot = payload.get("dot_number")
        mc = payload.get("mc_number")
        if step.name == "shield.safety_light" and cid:
            enqueue_safety_check(cid, dot, mc)
            return {**base, "result": "enqueued"}
        safer = fetch_safer(dot)
        light = score(safer)
        return {**base, "safety_light": light, "safer_status": safer}

    if step.name == "carrier.set_active":
        from ..supabase_client import get_supabase
        if cid:
            get_supabase().table("active_carriers").update(
                {"status": "active"}
            ).eq("id", cid).execute()
        return {**base, "status": "active"}

    if step.name == "lead.convert_to_carrier":
        from ..supabase_client import get_supabase
        lead_id = payload.get("lead_id")
        if lead_id:
            get_supabase().table("leads").update(
                {"stage": "converted", "carrier_id": cid}
            ).eq("id", lead_id).execute()
        return {**base, "converted": bool(lead_id)}

    # ── Dispatch ───────────────────────────────────────────────────────────────
    if step.name == "clm.scan_rate_conf":
        from ..clm.scanner import scan_contract
        text = payload.get("document_text", "")
        if text:
            extracted, conf, warnings = scan_contract(text, "rate_confirmation")
            return {**base, "confidence": conf, "warnings": warnings,
                    "extracted": extracted}
        return {**base, "result": "no_document_text"}

    if step.name == "nova.dispatch_email":
        from ..agents.nova import send_dispatch
        return {**base, **send_dispatch({**payload, "carrier_id": cid})}

    if step.name == "signal.dispatch_sms":
        from ..agents.signal import send_dispatch_sms
        return {**base, **send_dispatch_sms({**payload, "carrier_id": cid})}

    if step.name == "audit.fuel_advance":
        from ..agents.audit import decide_advance
        result = decide_advance(
            payload.get("driver_id", ""),
            float(payload.get("amount", 0)),
            float(payload.get("load_rate", 0)),
        )
        return {**base, **result}

    if step.name == "dispatch.match_truck":
        from ..agents.sonny import run as sonny_run
        return {**base, **sonny_run({**payload, "carrier_id": cid})}

    if step.name == "penny.margin_preview":
        rate = float(payload.get("rate_total", 0))
        fuel_est = float(payload.get("miles", 0)) * 0.55  # ~$0.55/mi fuel est
        driver_pay = rate * 0.72
        margin = rate - driver_pay - fuel_est
        return {**base, "gross": rate, "driver_pay": driver_pay,
                "fuel_est": fuel_est, "margin": margin, "margin_pct": margin / max(rate, 1)}

    if step.name in ("penny.fuel_cost_track", "penny.load_margin", "penny.update_mtd_kpis"):
        from ..agents.penny import run as penny_run
        action = step.name.split(".", 1)[1]
        result = penny_run({**payload, "carrier_id": cid, "action": action})
        return {**base, **result}

    if step.name in ("stripe.create_customer", "stripe.attach_subscription"):
        from ..agents.penny import create_checkout_session
        plan = payload.get("plan", "standard_5pct")
        email = payload.get("email", "")
        url = create_checkout_session(cid, plan, email) if cid else None
        return {**base, "checkout_url": url, "result": "checkout_created" if url else "stripe_skipped"}

    # ── Transit ────────────────────────────────────────────────────────────────
    if step.name in ("scout.extract_bol", "scout.extract_pod"):
        from ..agents.scout import run as scout_run
        return {**base, **scout_run({**payload, "carrier_id": cid})}

    if step.name == "signal.hos_warning":
        from ..agents.signal import send_hos_warning
        return {**base, **send_hos_warning({**payload, "carrier_id": cid})}

    if step.name == "signal.emergency_escalate":
        from ..agents.signal import send_emergency
        return {**base, **send_emergency({**payload, "carrier_id": cid})}

    if step.name == "orbit.geofence_delivery":
        from ..agents.orbit import run as orbit_run
        return {**base, **orbit_run(payload)}

    if step.name in ("atlas.checkcall_1", "atlas.checkcall_2", "atlas.checkcall_3"):
        from ..agents.nova import send_check_call
        return {**base, **send_check_call({**payload, "carrier_id": cid})}

    # ── Settlement ─────────────────────────────────────────────────────────────
    if step.name == "settler.calc_driver_pay":
        from ..agents.settler import calc_driver_payout
        driver_id = payload.get("driver_id", "")
        week_start = payload.get("week_start", "")
        week_end = payload.get("week_end", "")
        if driver_id and week_start and week_end:
            return {**base, **calc_driver_payout(driver_id, week_start, week_end)}
        return {**base, "result": "missing driver_id/week_start/week_end"}

    if step.name == "nova.settlement_email":
        from ..agents.nova import send_settlement
        return {**base, **send_settlement({**payload, "carrier_id": cid})}

    if step.name == "signal.cdl_alert":
        from ..agents.signal import send_cdl_alert
        return {**base, **send_cdl_alert({**payload, "carrier_id": cid})}

    # ── Compliance ─────────────────────────────────────────────────────────────
    if step.name in ("shield.cdl_sweep", "shield.cdl_expiry_check"):
        from ..agents.shield import check_cdl_expiry
        alerts = check_cdl_expiry(cid) if cid else []
        return {**base, "cdl_alerts": alerts}

    if step.name == "nova.compliance_alert":
        from ..agents.nova import send_compliance_alert
        return {**base, **send_compliance_alert({**payload, "carrier_id": cid})}

    # ── Analytics ──────────────────────────────────────────────────────────────
    if step.name in ("beacon.daily_digest", "beacon.activate_dashboard"):
        from ..agents.beacon import run as beacon_run
        return {**base, **beacon_run({**payload, "carrier_id": cid})}

    if step.name == "pulse.hos_monitor":
        from ..agents.pulse import score_driver
        driver_id = payload.get("driver_id", "")
        return {**base, **(score_driver(driver_id) if driver_id else {"note": "no driver_id"})}

    # ── Atlas state transitions ────────────────────────────────────────────────
    if step.name.startswith("atlas."):
        from ..agents.atlas import advance
        entity = payload.get("entity", "load")
        entity_id = payload.get("entity_id", "")
        from_state = payload.get("from_state", "")
        event = step.name.replace("atlas.", "")
        new_status = advance(entity, entity_id, from_state, event) if entity_id else None
        return {**base, "new_status": new_status}

    # ── Default: log intent and pass through ───────────────────────────────────
    return {
        **base,
        "description": step.description,
        "auto_trigger": step.auto_trigger,
        "requires_steps": step.requires_steps,
        "executed": True,
        "note": "step logged — integration pending for this step name",
    }

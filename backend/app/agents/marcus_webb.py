"""Marcus Webb — CLM Settlement & Compliance Manager.

Drives the downstream CLM lifecycle: rate benchmarking, blacklist enforcement,
auto-approval, milestone advancement, dispute escalation, GL posting, and
analytics refresh. Ensures every contract from intake to settlement is touched.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from ..logging_service import log_agent
from ..supabase_client import get_supabase


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _post_agent_log(action: str, result: str, payload: dict | None = None) -> None:
    log_agent("marcus_webb", action, payload=payload or {}, result=result)


# ── settlement pipeline ───────────────────────────────────────────────────────

def advance_milestones(limit: int = 100) -> dict[str, Any]:
    """Advance contract milestones based on presence of BOL and POD in vault.

    BOL present  → milestone_pct = 50 (pickup confirmed)
    POD present  → milestone_pct = 90 (delivery confirmed)
    Both present + invoice exists → eligible for 100%
    """
    from ..clm.engine import update_milestone  # noqa: PLC0415

    sb = get_supabase()
    active_contracts = (
        sb.table("contracts")
        .select("id,load_number,milestone_pct,contract_type,status")
        .eq("status", "active")
        .lt("milestone_pct", 90)
        .limit(limit)
        .execute()
        .data or []
    )

    advanced: list[dict] = []

    for c in active_contracts:
        cid = c["id"]
        load_num = c.get("load_number")
        current_pct = int(c.get("milestone_pct") or 0)

        # Check vault for BOL / POD linked to this contract or load_number
        q = sb.table("document_vault").select("doc_type")
        if load_num:
            q = q.eq("load_number", load_num)
        else:
            q = q.eq("contract_id", cid)

        docs = q.execute().data or []
        doc_types = {d["doc_type"] for d in docs}

        target_pct = current_pct
        if "pod" in doc_types and current_pct < 90:
            target_pct = 90
            note = "POD in vault — delivery confirmed"
        elif "bol" in doc_types and current_pct < 50:
            target_pct = 50
            note = "BOL in vault — pickup confirmed"
        else:
            continue

        if target_pct > current_pct:
            try:
                update_milestone(UUID(cid), target_pct, note)
                advanced.append({"contract_id": cid, "from": current_pct, "to": target_pct})
            except Exception:  # noqa: BLE001
                pass

    return {"milestone_advanced_count": len(advanced), "advanced": advanced}


def run_blacklist_sweep(limit: int = 50) -> dict[str, Any]:
    """Check recently scanned contracts against broker blacklist."""
    from ..clm.steps import step_129_broker_blacklist_check  # noqa: PLC0415

    sb = get_supabase()
    recent = (
        sb.table("contracts")
        .select("id,extracted_vars,flagged_for_review")
        .eq("flagged_for_review", False)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )

    flagged = 0
    for c in recent:
        evars = c.get("extracted_vars") or {}
        broker_mc = evars.get("broker_mc")
        if not broker_mc:
            continue
        result = step_129_broker_blacklist_check(None, UUID(c["id"]), {"broker_mc": broker_mc})
        if result.get("blacklisted"):
            flagged += 1

    return {"contracts_checked": len(recent), "newly_flagged": flagged}


def run_rate_benchmark_sweep(limit: int = 30) -> dict[str, Any]:
    """Benchmark recently scanned rate confirmations against market averages."""
    from ..clm.steps import step_130_rate_benchmark  # noqa: PLC0415

    sb = get_supabase()
    rate_cons = (
        sb.table("contracts")
        .select("id,rate_per_mile,extracted_vars")
        .eq("contract_type", "rate_confirmation")
        .not_.is_("rate_per_mile", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )

    below_market = 0
    above_market = 0
    at_market = 0

    for c in rate_cons:
        result = step_130_rate_benchmark(None, UUID(c["id"]), {
            "rate_per_mile": c.get("rate_per_mile"),
        })
        assessment = result.get("assessment", "unknown")
        if assessment == "below_market":
            below_market += 1
        elif assessment == "above_market":
            above_market += 1
        elif assessment == "at_market":
            at_market += 1

    return {
        "rate_cons_checked": len(rate_cons),
        "below_market": below_market,
        "at_market": at_market,
        "above_market": above_market,
    }


def run_auto_approve_sweep(limit: int = 50) -> dict[str, Any]:
    """Auto-approve contracts with confidence >= 90% that aren't yet approved."""
    from ..clm.steps import step_131_auto_approve  # noqa: PLC0415

    sb = get_supabase()
    candidates = (
        sb.table("contracts")
        .select("id,confidence_score,flagged_for_review,auto_approved")
        .eq("auto_approved", False)
        .eq("flagged_for_review", False)
        .gte("confidence_score", 0.90)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )

    approved = 0
    skipped = 0

    for c in candidates:
        result = step_131_auto_approve(None, UUID(c["id"]), {})
        if result.get("approved"):
            approved += 1
        else:
            skipped += 1

    return {
        "candidates": len(candidates),
        "auto_approved": approved,
        "skipped": skipped,
    }


def escalate_stale_disputes() -> dict[str, Any]:
    """Escalate open disputes older than 5 business days."""
    from ..clm.steps import step_142_dispute_escalate  # noqa: PLC0415
    result = step_142_dispute_escalate(None, None, {"threshold_days": 5})
    return result


def post_gl_for_complete_contracts(limit: int = 20) -> dict[str, Any]:
    """Post GL entries for 100% milestone contracts that haven't been GL-posted."""
    from ..clm.steps import step_137_gl_trigger  # noqa: PLC0415

    sb = get_supabase()
    ready = (
        sb.table("contracts")
        .select("id,milestone_pct,gl_posted,status")
        .gte("milestone_pct", 100)
        .eq("gl_posted", False)
        .neq("status", "archived")
        .limit(limit)
        .execute()
        .data or []
    )

    posted = 0
    for c in ready:
        result = step_137_gl_trigger(None, UUID(c["id"]), {})
        if result.get("gl_posted"):
            posted += 1

    return {"eligible": len(ready), "gl_posted": posted}


def refresh_analytics() -> dict[str, Any]:
    """Refresh today's CLM analytics snapshot."""
    from ..clm.steps import step_144_analytics_update  # noqa: PLC0415
    result = step_144_analytics_update(None, None, {})
    return result


def update_broker_scorecards(limit: int = 10) -> dict[str, Any]:
    """Update broker scorecards for top brokers by load volume."""
    from ..clm.steps import step_145_broker_scorecard  # noqa: PLC0415

    sb = get_supabase()
    top_brokers = (
        sb.table("broker_scorecards")
        .select("broker_mc")
        .order("total_loads", desc=True)
        .limit(limit)
        .execute()
        .data or []
    )

    updated = 0
    for b in top_brokers:
        result = step_145_broker_scorecard(None, None, {"broker_mc": b["broker_mc"]})
        if result.get("action") == "upserted":
            updated += 1

    return {"brokers_updated": updated}


# ── main entry point ──────────────────────────────────────────────────────────

def run(payload: dict[str, Any]) -> dict[str, Any]:
    """Daily CLM settlement sweep across all pipeline stages."""
    milestones   = advance_milestones()
    blacklist    = run_blacklist_sweep()
    benchmarks   = run_rate_benchmark_sweep()
    approvals    = run_auto_approve_sweep()
    disputes     = escalate_stale_disputes()
    gl           = post_gl_for_complete_contracts()
    analytics    = refresh_analytics()
    scorecards   = update_broker_scorecards()

    summary = (
        f"milestones_advanced={milestones['milestone_advanced_count']} "
        f"approved={approvals['auto_approved']} "
        f"blacklist_flagged={blacklist['newly_flagged']} "
        f"disputes_escalated={disputes.get('escalated_count', 0)} "
        f"gl_posted={gl['gl_posted']}"
    )

    _post_agent_log("clm_settlement_sweep", summary, payload={
        "milestones": milestones,
        "blacklist": blacklist,
        "benchmarks": benchmarks,
        "approvals": approvals,
        "disputes": disputes,
        "gl": gl,
        "analytics": analytics,
        "scorecards": scorecards,
    })

    return {
        "agent": "marcus_webb",
        "role": "CLM Settlement & Compliance Manager",
        "milestones": milestones,
        "blacklist_sweep": blacklist,
        "rate_benchmarks": benchmarks,
        "auto_approvals": approvals,
        "dispute_escalations": disputes,
        "gl_postings": gl,
        "analytics": analytics,
        "broker_scorecards": scorecards,
        "summary": summary,
        "ran_at": _now(),
    }

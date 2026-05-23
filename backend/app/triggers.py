"""Central trigger module — fires execution-engine domains in response to real events.

All `fire_*` functions are safe to call from any route handler.  They spawn a
daemon thread so they never block the HTTP response.

Trigger map
───────────
  carrier intake submitted  →  fire_onboarding(carrier_id)
  load status → Booked      →  fire_dispatch(carrier_id, load_id)
  load status → En Route    →  fire_transit(carrier_id, load_id)
  load status → Delivered   →  fire_settlement(carrier_id, load_id)
  daily 05:30 UTC cron      →  NEXUS prune (APScheduler)
  daily 06:00 UTC cron      →  fire_compliance_sweep()
  daily 06:30 UTC cron      →  fire_analytics_update()
  daily 06:45 UTC cron      →  fire_alexander()   — market intel (feeds Naomi)
  daily 07:00 UTC cron      →  fire_victoria()    — strategic snapshot
  daily 07:15 UTC cron      →  fire_naomi()       — lead scoring
  daily 07:30 UTC cron      →  fire_winston()     — carrier health + churn signals
  daily 08:00 UTC cron      →  fire_isabella()    — campaign builder (leads + re-engagement)
  daily 08:15 UTC cron      →  fire_sofia()       — financial reconciliation
  daily 09:00 UTC cron      →  fire_reagan_cole() — CLM intake & extraction sweep
  daily 09:30 UTC cron      →  fire_marcus_webb() — CLM settlement & compliance sweep
  vault doc uploaded/classified → fire_vault_scan(doc_id)
  contract scan complete    →  fire_clm_workflow(contract_id) — chain steps 124-131
"""
from __future__ import annotations

import threading
from typing import Any
from uuid import UUID

from .execution_engine.executor import run_domain, run_step
from .logging_service import get_logger

log = get_logger("3ll.triggers")


# ── internal helper ───────────────────────────────────────────────────────────

def _bg(fn, *args, **kwargs) -> None:
    """Run `fn(*args, **kwargs)` in a daemon thread — fire and forget."""
    t = threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True)
    t.start()


def _run_domain_safe(domain: str, carrier_id=None, contract_id=None, context: str = "") -> None:
    try:
        log.info("trigger domain=%s carrier=%s ctx=%s", domain, carrier_id, context)
        results = run_domain(domain, carrier_id, contract_id)
        ok = sum(1 for r in results if r.get("status") == "complete")
        fail = sum(1 for r in results if r.get("status") == "failed")
        log.info("trigger domain=%s done ok=%d fail=%d ctx=%s", domain, ok, fail, context)
    except Exception as exc:  # noqa: BLE001
        log.error("trigger domain=%s raised: %s ctx=%s", domain, exc, context)


def _run_step_safe(step_number: int, carrier_id=None, contract_id=None,
                   payload: dict | None = None, context: str = "") -> None:
    try:
        log.info("trigger step=%d carrier=%s ctx=%s", step_number, carrier_id, context)
        run_step(step_number, carrier_id, contract_id, payload or {})
    except Exception as exc:  # noqa: BLE001
        log.error("trigger step=%d raised: %s ctx=%s", step_number, exc, context)


# ── public fire_* functions ───────────────────────────────────────────────────

def fire_onboarding(carrier_id: str | UUID) -> None:
    """Trigger when a carrier intake form is submitted and carrier_id is known."""
    _bg(_run_domain_safe, "onboarding", carrier_id, None, f"intake:{carrier_id}")


def fire_dispatch(carrier_id: str | UUID | None, load_id: str,
                  payload: dict | None = None) -> None:
    """Trigger when a load is booked (status → Booked)."""
    _bg(_run_domain_safe, "dispatch", carrier_id, None, f"load_booked:{load_id}")


def fire_transit(carrier_id: str | UUID | None, load_id: str,
                 payload: dict | None = None) -> None:
    """Trigger when a driver confirms pickup (status → En Route)."""
    _bg(_run_domain_safe, "transit", carrier_id, None, f"pickup:{load_id}")


def fire_settlement(carrier_id: str | UUID | None, load_id: str,
                    payload: dict | None = None) -> None:
    """Trigger when a delivery is confirmed (status → Delivered / Completed)."""
    _bg(_run_domain_safe, "settlement", carrier_id, None, f"delivery:{load_id}")


def fire_compliance_sweep() -> None:
    """Trigger daily compliance domain sweep (no specific carrier — all carriers)."""
    _bg(_run_domain_safe, "compliance", None, None, "daily_cron")


def fire_analytics_update() -> None:
    """Trigger analytics domain (runs after settlement or on schedule)."""
    _bg(_run_domain_safe, "analytics", None, None, "analytics_refresh")


def fire_alexander() -> None:
    """Run Alexander Wright daily — market intelligence from FMCSA census."""
    def _run():
        try:
            from .agents.alexander import run as alexander_run  # noqa: PLC0415
            log.info("daily_agent: alexander starting")
            result = alexander_run({})
            log.info("daily_agent: alexander done states_analyzed=%s", result.get("states_analyzed"))
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: alexander failed: %s", exc)
    _bg(_run)


def fire_victoria() -> None:
    """Run Victoria Roth daily — strategic snapshot + org brain directive."""
    def _run():
        try:
            from .agents.victoria import run as victoria_run  # noqa: PLC0415
            log.info("daily_agent: victoria starting")
            result = victoria_run({})
            log.info("daily_agent: victoria done signals=%s", len(result.get("signals", [])))
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: victoria failed: %s", exc)
    _bg(_run)


def fire_naomi() -> None:
    """Run Naomi daily — lead scoring + FMCSA prospect pull."""
    def _run():
        try:
            from .agents.naomi import run as naomi_run  # noqa: PLC0415
            log.info("daily_agent: naomi starting")
            result = naomi_run({})
            log.info("daily_agent: naomi done leads_ranked=%s", result.get("leads_ranked"))
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: naomi failed: %s", exc)
    _bg(_run)


def fire_winston() -> None:
    """Run Winston Carmichael daily — carrier health + churn signals."""
    def _run():
        try:
            from .agents.winston import run as winston_run  # noqa: PLC0415
            log.info("daily_agent: winston starting")
            result = winston_run({})
            log.info(
                "daily_agent: winston done at_risk=%s retention=%s%%",
                result.get("at_risk_count"), result.get("retention_rate_pct"),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: winston failed: %s", exc)
    _bg(_run)


def fire_isabella() -> None:
    """Run Isabella Cruz daily — lead campaigns + carrier re-engagement."""
    def _run():
        try:
            from .agents.isabella import run as isabella_run  # noqa: PLC0415
            log.info("daily_agent: isabella starting (leads)")
            result_leads = isabella_run({"segment": "New", "limit": 50})
            log.info("daily_agent: isabella leads done size=%s", result_leads.get("campaign_size"))

            # Re-engagement campaign for at-risk carriers (reads Winston's carrier brain data)
            from .agents.isabella import run_carrier_reengagement  # noqa: PLC0415
            log.info("daily_agent: isabella starting (carrier re-engagement)")
            result_carriers = run_carrier_reengagement()
            log.info(
                "daily_agent: isabella re-engagement done targeted=%s",
                result_carriers.get("carriers_targeted"),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: isabella failed: %s", exc)
    _bg(_run)


def fire_sofia() -> None:
    """Run Sofia Chen daily — financial reconciliation."""
    def _run():
        try:
            from .agents.sofia import run as sofia_run  # noqa: PLC0415
            log.info("daily_agent: sofia starting")
            result = sofia_run({})
            log.info(
                "daily_agent: sofia done missing_invoices=%s collection_rate=%s%%",
                result.get("missing_invoices"), result.get("collection_rate_pct"),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: sofia failed: %s", exc)
    _bg(_run)


def fire_vance_batch() -> None:
    """Run Vance batch daily — outbound calls to high-score leads (score >= 8)."""
    def _run():
        try:
            from .agents.vance import run_batch  # noqa: PLC0415
            log.info("daily_agent: vance_batch starting")
            result = run_batch()
            log.info(
                "daily_agent: vance_batch done queued=%s errors=%s",
                result.get("calls_queued"), result.get("errors"),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: vance_batch failed: %s", exc)
    _bg(_run)


def fire_sms_campaign() -> None:
    """Run SMS campaigner daily — bulk SMS to Tier B leads (score 4-7)."""
    def _run():
        try:
            from .agents.sms_campaigner import send_batch  # noqa: PLC0415
            log.info("daily_agent: sms_campaign starting")
            result = send_batch()
            log.info(
                "daily_agent: sms_campaign done sent=%s failed=%s",
                result.get("sent"), result.get("failed"),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: sms_campaign failed: %s", exc)
    _bg(_run)


def fire_email_campaign() -> None:
    """Run email campaigner daily — cold outreach to leads with email addresses."""
    def _run():
        try:
            from .agents.email_campaigner import send_batch  # noqa: PLC0415
            log.info("daily_agent: email_campaign starting")
            result = send_batch()
            log.info(
                "daily_agent: email_campaign done sent=%s failed=%s",
                result.get("sent"), result.get("failed"),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: email_campaign failed: %s", exc)
    _bg(_run)


def fire_social_post() -> None:
    """Run social poster weekly — posts to Facebook, Instagram, LinkedIn."""
    def _run():
        try:
            from .agents.social import post_all  # noqa: PLC0415
            log.info("weekly_agent: social_post starting")
            result = post_all()
            log.info(
                "weekly_agent: social_post done fb=%s ig=%s li=%s",
                result.get("facebook", {}).get("status"),
                result.get("instagram", {}).get("status"),
                result.get("linkedin", {}).get("status"),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("weekly_agent: social_post failed: %s", exc)
    _bg(_run)


def fire_mark_odom() -> None:
    """Run Mark Odom daily — Commander brief + tier-3 review + strategic directives."""
    def _run():
        try:
            from .agents.mark_odom import run as mark_odom_run  # noqa: PLC0415
            log.info("daily_agent: mark_odom starting")
            result = mark_odom_run({})
            log.info(
                "daily_agent: mark_odom done decisions=%s tier3_open=%s",
                len(result.get("commander_decisions", [])),
                result.get("fleet_metrics", {}).get("open_tier3_escalations"),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: mark_odom failed: %s", exc)
    _bg(_run)


def fire_cc_gulley() -> None:
    """Run CC Gulley daily — strategic plan + 30/60/90-day roadmap + risk assessment."""
    def _run():
        try:
            from .agents.cc_gulley import run as cc_gulley_run  # noqa: PLC0415
            log.info("daily_agent: cc_gulley starting")
            result = cc_gulley_run({})
            log.info(
                "daily_agent: cc_gulley done priorities=%s risks=%s",
                len(result.get("priorities_30d", [])),
                len(result.get("strategic_risks", [])),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: cc_gulley failed: %s", exc)
    _bg(_run)


def fire_follow_up_reminders() -> None:
    """Hourly job — sends 24h SMS reminders to Interested leads whose time has come."""
    def _run():
        try:
            from .prospecting.follow_up import send_due_reminders  # noqa: PLC0415
            result = send_due_reminders()
            log.info("fire_follow_up_reminders sent=%s eligible=%s",
                     result.get("sent"), result.get("eligible"))
        except Exception as exc:  # noqa: BLE001
            log.error("fire_follow_up_reminders failed: %s", exc)
    _bg(_run)


def fire_reagan_cole() -> None:
    """Run Reagan Cole daily — CLM intake & extraction sweep."""
    def _run():
        try:
            from .agents.reagan_cole import run as reagan_run  # noqa: PLC0415
            log.info("daily_agent: reagan_cole starting")
            result = reagan_run({})
            log.info(
                "daily_agent: reagan_cole done backlog=%s requeued=%s avg_conf=%s",
                result.get("pipeline_health", {}).get("extraction_backlog"),
                result.get("vault_audit", {}).get("requeued"),
                result.get("extraction_metrics", {}).get("avg_confidence"),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: reagan_cole failed: %s", exc)
    _bg(_run)


def fire_marcus_webb() -> None:
    """Run Marcus Webb daily — CLM settlement & compliance sweep."""
    def _run():
        try:
            from .agents.marcus_webb import run as marcus_run  # noqa: PLC0415
            log.info("daily_agent: marcus_webb starting")
            result = marcus_run({})
            log.info(
                "daily_agent: marcus_webb done approved=%s gl_posted=%s disputes=%s",
                result.get("auto_approvals", {}).get("auto_approved"),
                result.get("gl_postings", {}).get("gl_posted"),
                result.get("dispute_escalations", {}).get("escalated_count"),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("daily_agent: marcus_webb failed: %s", exc)
    _bg(_run)


def fire_clm_workflow(contract_id: str, carrier_id: str | None = None) -> None:
    """Chain CLM steps 124-131 after a contract has been scanned (step 123 done).

    Called automatically after extract_vault_doc completes on a contract-linked doc.
    Runs: digital_twin → revenue_leakage → counterparty_lookup → duplicate_detect
          → expiry_schedule → blacklist_check → rate_benchmark → auto_approve
    """
    def _run():
        try:
            from .execution_engine.executor import run_step  # noqa: PLC0415
            from uuid import UUID  # noqa: PLC0415
            cid = UUID(contract_id)
            vid = UUID(carrier_id) if carrier_id else None
            for step_num in (124, 125, 126, 127, 128, 129, 130, 131):
                try:
                    run_step(step_num, vid, cid, {})
                except Exception as exc:  # noqa: BLE001
                    log.warning("fire_clm_workflow step=%d contract=%s: %s", step_num, contract_id, exc)
            log.info("fire_clm_workflow complete contract=%s", contract_id)
        except Exception as exc:  # noqa: BLE001
            log.error("fire_clm_workflow failed contract=%s: %s", contract_id, exc)
    t = threading.Thread(target=_run, daemon=True)
    t.start()


def fire_vault_scan(doc_id: str) -> None:
    """Trigger background AI extraction for a vault document.

    Called after upload or classification for scannable doc types
    (rate_con, bol, pod, broker_agreement).
    """
    def _scan():
        try:
            from .clm.doc_extractor import extract_vault_doc  # noqa: PLC0415
            log.info("fire_vault_scan doc_id=%s", doc_id)
            result = extract_vault_doc(doc_id)
            log.info(
                "fire_vault_scan complete doc_id=%s method=%s confidence=%.3f",
                doc_id, result.get("method"), result.get("confidence", 0),
            )
        except Exception as exc:  # noqa: BLE001
            log.error("fire_vault_scan failed doc_id=%s: %s", doc_id, exc)

    t = threading.Thread(target=_scan, daemon=True)
    t.start()


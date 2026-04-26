"""Step registry — all 200 autonomous execution steps across 7 domains."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Step:
    number: int
    name: str
    domain: str
    description: str
    auto_trigger: bool = True
    requires_steps: list[int] = field(default_factory=list)


STEP_REGISTRY: dict[int, Step] = {}


def _reg(*steps: Step) -> None:
    for s in steps:
        STEP_REGISTRY[s.number] = s


# ── DOMAIN 1: CARRIER ONBOARDING (1–30) ──────────────────────────────────────
_reg(
    Step(1,  "intake.receive",            "onboarding", "Receive carrier intake form submission"),
    Step(2,  "intake.dedupe_check",       "onboarding", "Deduplicate carrier by MC/DOT/EIN", requires_steps=[1]),
    Step(3,  "fmcsa.lookup",              "onboarding", "Query FMCSA SAFER API for authority status", requires_steps=[2]),
    Step(4,  "fmcsa.csa_score",           "onboarding", "Pull CSA BASIC scores from FMCSA", requires_steps=[3]),
    Step(5,  "shield.safety_light",       "onboarding", "Evaluate safety light (green/yellow/red)", requires_steps=[4]),
    Step(6,  "insurance.verify",          "onboarding", "Verify insurance certificates via FMCSA", requires_steps=[3]),
    Step(7,  "insurance.expiry_watch",    "onboarding", "Schedule insurance expiry alert", requires_steps=[6]),
    Step(8,  "eld.detect_provider",       "onboarding", "Detect ELD provider (Motive/Samsara/Geotab)", requires_steps=[1]),
    Step(9,  "eld.sync_credentials",      "onboarding", "Sync ELD API credentials to fleet record", requires_steps=[8]),
    Step(10, "banking.collect",           "onboarding", "Collect banking / ACH information", requires_steps=[1]),
    Step(11, "banking.verify",            "onboarding", "Micro-deposit or Plaid verification of bank account", requires_steps=[10]),
    Step(12, "stripe.create_customer",    "onboarding", "Create Stripe customer record", requires_steps=[1]),
    Step(13, "stripe.attach_subscription","onboarding", "Attach founders/pro subscription plan", requires_steps=[12]),
    Step(14, "esign.send_agreement",      "onboarding", "Send carrier agreement for e-signature", requires_steps=[5, 6]),
    Step(15, "esign.track_completion",    "onboarding", "Poll e-signature status until complete", requires_steps=[14]),
    Step(16, "clm.ingest_agreement",      "onboarding", "Ingest signed carrier agreement into CLM", requires_steps=[15]),
    Step(17, "carrier.set_active",        "onboarding", "Set carrier status to active", requires_steps=[15, 11]),
    Step(18, "inventory.decrement",       "onboarding", "Decrement founders inventory slot", requires_steps=[17]),
    Step(19, "nova.welcome_email",        "onboarding", "Send welcome email via Postmark", requires_steps=[17]),
    Step(20, "vance.welcome_call",        "onboarding", "Trigger Vapi welcome/onboarding voice call", requires_steps=[17]),
    Step(21, "document_vault.create_folder", "onboarding", "Create carrier document vault folder", requires_steps=[17]),
    Step(22, "document_vault.upload_agreement", "onboarding", "Upload signed agreement to document vault", requires_steps=[16, 21]),
    Step(23, "atlas.schedule_check_in",   "onboarding", "Schedule 7-day check-in with carrier", requires_steps=[17]),
    Step(24, "beacon.activate_dashboard", "onboarding", "Activate carrier in command center dashboard", requires_steps=[17]),
    Step(25, "mc_loyalty.check",          "onboarding", "Check MC loyalty — canceled MCs get $400 rate tier", requires_steps=[3]),
    Step(26, "lead.convert_to_carrier",   "onboarding", "Convert lead record to active carrier", requires_steps=[17]),
    Step(27, "airtable.sync_record",      "onboarding", "Sync carrier record to Airtable", requires_steps=[17]),
    Step(28, "signal.notify_commander",   "onboarding", "Notify Commander of new carrier activation", requires_steps=[17]),
    Step(29, "fleet.create_asset",        "onboarding", "Create fleet asset record for each truck", requires_steps=[17]),
    Step(30, "onboarding.complete",       "onboarding", "Mark onboarding complete — write atomic ledger event", requires_steps=list(range(17, 30))),
)

# ── DOMAIN 2: LOAD DISPATCH (31–60) ──────────────────────────────────────────
_reg(
    Step(31, "dispatch.load_received",    "dispatch", "Receive new load from broker or shipper"),
    Step(32, "clm.scan_rate_conf",        "dispatch", "Scan rate confirmation with Claude CLM scanner", requires_steps=[31]),
    Step(33, "clm.validate_rate",         "dispatch", "Validate rate against market benchmarks", requires_steps=[32]),
    Step(34, "dispatch.match_truck",      "dispatch", "Match load to available truck by equipment/HOS/location", requires_steps=[32]),
    Step(35, "dispatch.score_match",      "dispatch", "Score truck-load match (proximity, margin, HOS hours)", requires_steps=[34]),
    Step(36, "dispatch.offer_load",       "dispatch", "Offer load to driver via PWA notification", requires_steps=[35]),
    Step(37, "dispatch.driver_accept",    "dispatch", "Receive driver acceptance from PWA", requires_steps=[36]),
    Step(38, "dispatch.reoffer_on_decline","dispatch", "Re-offer to next ranked truck if declined", requires_steps=[36]),
    Step(39, "eld.lock_hos",              "dispatch", "Lock driver HOS hours in ELD for this load", requires_steps=[37]),
    Step(40, "clm.create_load_contract",  "dispatch", "Create contract record linking rate conf to load", requires_steps=[32, 37]),
    Step(41, "dispatch.confirm_broker",   "dispatch", "Send load acceptance confirmation to broker", requires_steps=[37]),
    Step(42, "nova.dispatch_email",       "dispatch", "Email dispatch sheet to driver and broker", requires_steps=[37]),
    Step(43, "signal.dispatch_sms",       "dispatch", "SMS load details to driver", requires_steps=[37]),
    Step(44, "orbit.start_tracking",      "dispatch", "Begin GPS tracking session for this load", requires_steps=[37]),
    Step(45, "audit.fuel_advance",        "dispatch", "Evaluate and approve/deny fuel advance request", requires_steps=[37]),
    Step(46, "dispatch.log_event",        "dispatch", "Write dispatch event to atomic ledger", requires_steps=[40]),
    Step(47, "sonny.post_loadboard",      "dispatch", "Post to DAT/Truckstop if spot load", requires_steps=[31]),
    Step(48, "dispatch.eta_calculate",    "dispatch", "Calculate ETA based on origin, destination, HOS", requires_steps=[34]),
    Step(49, "penny.margin_preview",      "dispatch", "Pre-dispatch margin preview (rate - fuel - driver %)", requires_steps=[33, 48]),
    Step(50, "dispatch.assign_load_id",   "dispatch", "Assign internal load ID and write to DB", requires_steps=[37]),
    Step(51, "dispatch.notify_shipper",   "dispatch", "Notify shipper of driver name, truck#, ETA", requires_steps=[37, 48]),
    Step(52, "dispatch.schedule_checkcall_1", "dispatch", "Schedule first check call (pickup +2hr)", requires_steps=[37]),
    Step(53, "dispatch.schedule_checkcall_2", "dispatch", "Schedule mid-transit check call", requires_steps=[37]),
    Step(54, "dispatch.schedule_checkcall_3", "dispatch", "Schedule pre-delivery check call", requires_steps=[37]),
    Step(55, "fleet.status_intransit",    "dispatch", "Update truck status to in_transit", requires_steps=[37]),
    Step(56, "document_vault.expect_bol", "dispatch", "Set expectation: BOL required within 2hr of pickup", requires_steps=[37]),
    Step(57, "dispatch.rate_lock",        "dispatch", "Lock rate — prevent re-negotiation post-dispatch", requires_steps=[41]),
    Step(58, "dispatch.insurance_check",  "dispatch", "Verify truck insurance current before dispatch", requires_steps=[6]),
    Step(59, "shield.pre_dispatch_safety","dispatch", "Pre-dispatch safety check (CSA, violations)", requires_steps=[37]),
    Step(60, "dispatch.complete",         "dispatch", "Mark dispatch complete — write atomic ledger event", requires_steps=[46, 55]),
)

# ── DOMAIN 3: IN-TRANSIT OPERATIONS (61–90) ──────────────────────────────────
_reg(
    Step(61, "transit.pickup_confirmed",  "transit", "Confirm pickup via GPS geofence or driver PWA tap"),
    Step(62, "document_vault.upload_bol", "transit", "Driver uploads BOL via PWA after pickup", requires_steps=[61]),
    Step(63, "scout.extract_bol",         "transit", "Scout extracts BOL data with Claude scanner", requires_steps=[62]),
    Step(64, "clm.link_bol_to_contract",  "transit", "Link BOL data to contract record", requires_steps=[63]),
    Step(65, "orbit.gps_ping_loop",       "transit", "Continuous GPS ping every 5 min from ELD", requires_steps=[61]),
    Step(66, "pulse.hos_monitor",         "transit", "Monitor driver HOS — alert at 2hr remaining", requires_steps=[65]),
    Step(67, "signal.hos_warning",        "transit", "SMS driver and Commander if HOS < 2hr", requires_steps=[66]),
    Step(68, "atlas.checkcall_1",         "transit", "Execute first automated check call via Vapi", requires_steps=[52]),
    Step(69, "atlas.checkcall_2",         "transit", "Execute mid-transit check call via Vapi", requires_steps=[53]),
    Step(70, "signal.delay_alert",        "transit", "Alert broker/shipper if ETA slips > 2hr", requires_steps=[65, 48]),
    Step(71, "orbit.geofence_delivery",   "transit", "Watch for truck entry into delivery geofence", requires_steps=[65]),
    Step(72, "atlas.checkcall_3",         "transit", "Execute pre-delivery check call", requires_steps=[54]),
    Step(73, "transit.weather_check",     "transit", "Check weather along route for delay risk", requires_steps=[65]),
    Step(74, "transit.traffic_check",     "transit", "Check traffic — update ETA if needed", requires_steps=[65]),
    Step(75, "signal.breakdown_detect",   "transit", "Detect breakdown: truck stopped >30min off-route", requires_steps=[65]),
    Step(76, "signal.emergency_escalate", "transit", "Escalate emergency via SMS to Commander", requires_steps=[75]),
    Step(77, "transit.detention_clock",   "transit", "Start detention timer if waiting >2hr at shipper", requires_steps=[61]),
    Step(78, "transit.detention_notify",  "transit", "Notify broker of detention accrual", requires_steps=[77]),
    Step(79, "transit.lumper_approve",    "transit", "Approve lumper receipt for reimbursement", requires_steps=[61]),
    Step(80, "penny.fuel_cost_track",     "transit", "Track fuel purchases via fuel card for this load", requires_steps=[61]),
    Step(81, "transit.mid_route_safety",  "transit", "Mid-route safety check — CSA score still valid", requires_steps=[65]),
    Step(82, "transit.broker_visibility", "transit", "Push live truck location to broker portal", requires_steps=[65]),
    Step(83, "transit.eta_sms_update",    "transit", "Send automated ETA update SMS to consignee", requires_steps=[74]),
    Step(84, "transit.dock_schedule",     "transit", "Auto-schedule dock appointment at destination", requires_steps=[48]),
    Step(85, "transit.hos_remaining",     "transit", "Calculate HOS hours remaining at destination", requires_steps=[66]),
    Step(86, "transit.border_crossing",   "transit", "Handle CTPAT/CBP docs if crossing border", requires_steps=[32]),
    Step(87, "transit.hazmat_compliance", "transit", "Verify hazmat placard and manifest if applicable", requires_steps=[32]),
    Step(88, "transit.temp_monitoring",   "transit", "Monitor reefer temperature for temp-sensitive loads", requires_steps=[65]),
    Step(89, "transit.cargo_claim_detect","transit", "Detect cargo claim risk from damage report", requires_steps=[61]),
    Step(90, "transit.complete",          "transit", "Mark transit complete on delivery geofence entry", requires_steps=[71]),
)

# ── DOMAIN 4: DELIVERY & SETTLEMENT (91–120) ─────────────────────────────────
_reg(
    Step(91,  "delivery.confirmed",          "settlement", "Confirm delivery via GPS geofence or driver PWA"),
    Step(92,  "document_vault.upload_pod",   "settlement", "Driver uploads POD via PWA", requires_steps=[91]),
    Step(93,  "scout.extract_pod",           "settlement", "Scout extracts POD data with Claude scanner", requires_steps=[92]),
    Step(94,  "clm.link_pod_to_contract",    "settlement", "Link POD to contract, set milestone to 100%", requires_steps=[93]),
    Step(95,  "clm.trigger_invoice",         "settlement", "Trigger invoice generation from contract", requires_steps=[94]),
    Step(96,  "echo.missing_doc_check",      "settlement", "If delivered but no POD in 4hr → SMS nudge", requires_steps=[91]),
    Step(97,  "settler.calc_driver_pay",     "settlement", "Calculate driver gross pay (rate% minus deductions)", requires_steps=[95]),
    Step(98,  "settler.fuel_deduction",      "settlement", "Apply fuel card deductions to settlement", requires_steps=[80, 97]),
    Step(99,  "settler.escrow_check",        "settlement", "Check escrow balance and apply if applicable", requires_steps=[97]),
    Step(100, "settler.lumper_reimbursement","settlement", "Add lumper reimbursement to settlement", requires_steps=[79, 97]),
    Step(101, "settler.detention_add",       "settlement", "Add approved detention pay to settlement", requires_steps=[78, 97]),
    Step(102, "settler.advance_deduct",      "settlement", "Deduct fuel/cash advances from settlement", requires_steps=[45, 97]),
    Step(103, "settler.net_pay_calc",        "settlement", "Calculate final net driver pay", requires_steps=[97, 98, 99, 100, 101, 102]),
    Step(104, "penny.load_margin",           "settlement", "Calculate final load margin (gross minus all costs)", requires_steps=[103]),
    Step(105, "settler.ach_initiate",        "settlement", "Initiate ACH payment to driver bank account", requires_steps=[103, 11]),
    Step(106, "nova.settlement_email",       "settlement", "Email settlement statement to driver", requires_steps=[103]),
    Step(107, "factoring.submit_invoice",    "settlement", "Submit invoice to factoring company", requires_steps=[95]),
    Step(108, "factoring.track_payment",     "settlement", "Track factoring payment status", requires_steps=[107]),
    Step(109, "clm.mark_gl_posted",          "settlement", "Mark contract as GL posted in accounting", requires_steps=[95]),
    Step(110, "penny.update_mtd_kpis",       "settlement", "Update MTD KPIs: gross, margin, RPM", requires_steps=[104]),
    Step(111, "fleet.status_available",      "settlement", "Set truck status back to available", requires_steps=[91]),
    Step(112, "dispatch.next_load_offer",    "settlement", "Proactively offer next load within 50mi", requires_steps=[111]),
    Step(113, "audit.settlement_audit",      "settlement", "Audit settlement for SOD compliance", requires_steps=[105]),
    Step(114, "beacon.update_load_history",  "settlement", "Update load history in command center", requires_steps=[110]),
    Step(115, "atomic_ledger.settlement",    "settlement", "Write complete settlement event to atomic ledger", requires_steps=[109, 110]),
    Step(116, "driver.performance_score",    "settlement", "Update driver performance score after delivery", requires_steps=[91, 93]),
    Step(117, "carrier.revenue_update",      "settlement", "Update carrier MTD revenue record", requires_steps=[110]),
    Step(118, "nova.broker_invoice_email",   "settlement", "Email invoice/POD package to broker", requires_steps=[93, 95]),
    Step(119, "dispute.check_variance",      "settlement", "Check if paid amount matches rate confirmation", requires_steps=[108, 95]),
    Step(120, "settlement.complete",         "settlement", "Mark settlement complete, archive to vault", requires_steps=[115]),
)

# ── DOMAIN 5: CONTRACT LIFECYCLE MANAGEMENT (121–150) ────────────────────────
_reg(
    Step(121, "clm.email_inbound_parse",   "clm", "Parse SendGrid inbound email for contract attachments"),
    Step(122, "clm.doc_classify",          "clm", "Classify document type: rate_conf/bol/pod/agreement", requires_steps=[121]),
    Step(123, "clm.extract_variables",     "clm", "Run Claude scanner to extract 100+ contract variables", requires_steps=[122]),
    Step(124, "clm.digital_twin_create",   "clm", "Create contract digital twin in Supabase", requires_steps=[123]),
    Step(125, "clm.revenue_leakage_check", "clm", "Compare actual billing vs. contract terms", requires_steps=[124]),
    Step(126, "clm.counterparty_lookup",   "clm", "Lookup broker/shipper in carrier records DB", requires_steps=[124]),
    Step(127, "clm.duplicate_detect",      "clm", "Detect duplicate rate confirmations (same load#)", requires_steps=[124]),
    Step(128, "clm.expiry_schedule",       "clm", "Schedule alerts for contract/agreement expiry", requires_steps=[124]),
    Step(129, "clm.broker_blacklist_check","clm", "Check broker against known bad-pay list", requires_steps=[126]),
    Step(130, "clm.rate_benchmark",        "clm", "Compare rate against DAT/Truckstop spot market", requires_steps=[123]),
    Step(131, "clm.auto_approve",          "clm", "Auto-approve contract if confidence >90% and no warnings", requires_steps=[125, 129, 130]),
    Step(132, "clm.flag_for_review",       "clm", "Flag contract for Commander review if warnings exist", requires_steps=[123]),
    Step(133, "clm.milestone_10pct",       "clm", "Set milestone 10% on load assignment", requires_steps=[124]),
    Step(134, "clm.milestone_50pct",       "clm", "Set milestone 50% on pickup confirmed", requires_steps=[133]),
    Step(135, "clm.milestone_90pct",       "clm", "Set milestone 90% on POD uploaded", requires_steps=[134]),
    Step(136, "clm.milestone_100pct",      "clm", "Set milestone 100% on invoice paid", requires_steps=[135]),
    Step(137, "clm.gl_trigger",            "clm", "Trigger GL/accounting entry at 100% milestone", requires_steps=[136]),
    Step(138, "clm.factoring_eligibility", "clm", "Check contract eligibility for factoring", requires_steps=[124]),
    Step(139, "clm.broker_agreement_link", "clm", "Link rate confirmation to master broker agreement", requires_steps=[124]),
    Step(140, "clm.payment_terms_enforce", "clm", "Enforce payment terms — flag if overdue", requires_steps=[124]),
    Step(141, "clm.dispute_open",          "clm", "Open dispute record if payment variance detected", requires_steps=[119]),
    Step(142, "clm.dispute_escalate",      "clm", "Escalate dispute to Commander after 5 business days", requires_steps=[141]),
    Step(143, "clm.archive_executed",      "clm", "Archive fully executed contract with all documents", requires_steps=[136]),
    Step(144, "clm.analytics_update",      "clm", "Update CLM analytics: avg rate/mi, payment cycle time", requires_steps=[136]),
    Step(145, "clm.broker_scorecard",      "clm", "Update broker reliability scorecard", requires_steps=[136]),
    Step(146, "clm.volume_discount_check", "clm", "Check if broker qualifies for volume discount tier", requires_steps=[145]),
    Step(147, "clm.auto_renew_agreement",  "clm", "Auto-renew expired broker agreement if in good standing", requires_steps=[128]),
    Step(148, "clm.contract_export",       "clm", "Export contract package (PDF+JSON) for enterprise clients", requires_steps=[143]),
    Step(149, "clm.compliance_audit",      "clm", "Run compliance audit on contract (SOD, GAAP mapping)", requires_steps=[143]),
    Step(150, "clm.complete",              "clm", "Mark CLM workflow complete — write atomic ledger event", requires_steps=[143, 144]),
)

# ── DOMAIN 6: COMPLIANCE & SAFETY (151–180) ──────────────────────────────────
_reg(
    Step(151, "shield.daily_sweep",        "compliance", "Daily sweep of all 1000 trucks for safety status"),
    Step(152, "shield.csa_refresh",        "compliance", "Refresh CSA BASIC scores weekly from FMCSA", requires_steps=[151]),
    Step(153, "shield.insurance_30d",      "compliance", "Alert 30 days before insurance expiry", requires_steps=[151]),
    Step(154, "shield.insurance_7d",       "compliance", "Urgent alert 7 days before insurance expiry", requires_steps=[153]),
    Step(155, "shield.insurance_expired",  "compliance", "Auto-suspend carrier if insurance expired", requires_steps=[154]),
    Step(156, "shield.mc_authority_check", "compliance", "Verify MC authority still active in FMCSA SAFER", requires_steps=[151]),
    Step(157, "shield.cdl_expiry_check",   "compliance", "Check CDL expiry for all active drivers", requires_steps=[151]),
    Step(158, "shield.cdl_expiry_30d",     "compliance", "Alert driver and carrier 30 days before CDL expiry", requires_steps=[157]),
    Step(159, "shield.cdl_expiry_7d",      "compliance", "Urgent alert 7 days before CDL expiry — suspend if expired", requires_steps=[158]),
    Step(160, "shield.drug_test_schedule", "compliance", "Schedule random drug testing per DOT requirements", requires_steps=[151]),
    Step(161, "shield.accident_flag",      "compliance", "Flag carrier with DOT accident report in last 12mo", requires_steps=[152]),
    Step(162, "shield.oos_rate_check",     "compliance", "Flag if Out-of-Service rate exceeds 20% threshold", requires_steps=[152]),
    Step(163, "shield.safety_light_update","compliance", "Update safety light color based on all compliance factors", requires_steps=[152, 156, 157]),
    Step(164, "shield.red_light_suspend",  "compliance", "Block load offers to red-light carriers", requires_steps=[163]),
    Step(165, "nova.compliance_email",     "compliance", "Email compliance status report to carrier", requires_steps=[163]),
    Step(166, "signal.compliance_sms",     "compliance", "SMS carrier if safety light turns yellow or red", requires_steps=[163]),
    Step(167, "shield.hazmat_cert_check",  "compliance", "Verify hazmat endorsement for hazmat trucks", requires_steps=[151]),
    Step(168, "shield.oversize_permit",    "compliance", "Verify oversize/overweight permits are current", requires_steps=[151]),
    Step(169, "shield.ifta_compliance",    "compliance", "Check IFTA quarterly filing status", requires_steps=[151]),
    Step(170, "shield.ucr_registration",   "compliance", "Verify UCR registration is current", requires_steps=[151]),
    Step(171, "shield.annual_inspection",  "compliance", "Track annual vehicle inspection compliance", requires_steps=[151]),
    Step(172, "shield.dot_audit_prep",     "compliance", "Generate DOT audit readiness report", requires_steps=[152, 163]),
    Step(173, "shield.eld_mandate_check",  "compliance", "Verify ELD mandate compliance for all trucks", requires_steps=[151]),
    Step(174, "shield.cargo_insurance",    "compliance", "Verify per-load cargo insurance meets broker minimum", requires_steps=[32]),
    Step(175, "shield.new_entrant_monitor","compliance", "Monitor new authority carriers (<12 months) for violations", requires_steps=[3]),
    Step(176, "shield.driver_mvr_check",   "compliance", "Annual MVR check for all drivers", requires_steps=[151]),
    Step(177, "shield.lease_agreement",    "compliance", "Verify owner-operator lease agreements are current", requires_steps=[151]),
    Step(178, "shield.escrow_audit",       "compliance", "Audit escrow accounts for regulatory compliance", requires_steps=[99]),
    Step(179, "shield.compliance_score",   "compliance", "Calculate composite compliance score (0–100) per carrier", requires_steps=[163, 169, 170, 171]),
    Step(180, "compliance.complete",       "compliance", "Write compliance cycle results to atomic ledger", requires_steps=[179]),
)

# ── DOMAIN 7: ANALYTICS & INTELLIGENCE (181–200) ─────────────────────────────
_reg(
    Step(181, "analytics.daily_kpi",        "analytics", "Refresh all KPIs: gross, margin, RPM, utilization"),
    Step(182, "analytics.fleet_utilization","analytics", "Calculate fleet utilization rate (active/total)", requires_steps=[181]),
    Step(183, "analytics.lane_profitability","analytics", "Analyze profitability by lane (origin-dest pair)", requires_steps=[181]),
    Step(184, "analytics.broker_performance","analytics", "Rank brokers by pay speed, rate quality, dispute rate", requires_steps=[144, 145]),
    Step(185, "analytics.driver_ranking",   "analytics", "Update driver performance ranking", requires_steps=[116]),
    Step(186, "analytics.revenue_forecast", "analytics", "30/60/90-day revenue forecast from load history", requires_steps=[183]),
    Step(187, "analytics.fuel_analysis",    "analytics", "Analyze fuel cost trends and efficiency by truck", requires_steps=[80]),
    Step(188, "analytics.dead_head_report", "analytics", "Report dead-head miles per truck", requires_steps=[182]),
    Step(189, "analytics.detention_report", "analytics", "Summarize detention events by broker/shipper", requires_steps=[78]),
    Step(190, "analytics.spot_vs_contract", "analytics", "Compare spot vs. contract rate performance", requires_steps=[130]),
    Step(191, "analytics.cash_flow",        "analytics", "Project cash flow based on factoring and settlement cycles", requires_steps=[186]),
    Step(192, "analytics.carrier_ltv",      "analytics", "Calculate carrier lifetime value (subscription + load revenue)", requires_steps=[117]),
    Step(193, "analytics.csa_trend",        "analytics", "Track CSA score trends — predict carrier risk trajectory", requires_steps=[152]),
    Step(194, "analytics.rate_index",       "analytics", "Build internal rate index from all executed rate confs", requires_steps=[150]),
    Step(195, "analytics.equipment_demand", "analytics", "Forecast equipment demand by type", requires_steps=[183]),
    Step(196, "analytics.compliance_risk",  "analytics", "Score fleet compliance risk for insurance renewal", requires_steps=[179]),
    Step(197, "analytics.weekly_report",    "analytics", "Generate weekly executive report for Commander", requires_steps=[181, 182, 183]),
    Step(198, "analytics.airtable_sync",    "analytics", "Sync analytics summary to Airtable", requires_steps=[197]),
    Step(199, "analytics.sentry_health",    "analytics", "Check Sentry error rates and alert if elevated"),
    Step(200, "analytics.complete",         "analytics", "Mark analytics cycle complete — write atomic ledger event", requires_steps=[197]),
)

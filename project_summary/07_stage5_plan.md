# 07 — Stage 5 Plan (Steps 61–100)

Stage 5 deepens and connects the scaffolds from Stages 2–4: turn stubs into
production behavior, close auth/billing, ship background jobs, and light up
observability. Grouped into four phases (10 steps each).

## Phase 5A — Agent behaviors (61–70)
Turn each agent stub into a working module with real tool calls + tests.

- 61. Vance orchestration loop — task queue pull, per-agent dispatch, audit trail
- 62. Sonny load-match — rank loads for each truck by lane/weight/HOS
- 63. Shield live checks — FMCSA pull, COI expiry, Clearinghouse nightly
- 64. Scout ingest → score → route into `lead_pipeline`
- 65. Penny billing — Stripe usage events, dunning, plan changes
- 66. Settler weekly run — driver settlement packet generation + ACH push
- 67. Audit doc pipeline — OCR + field extraction for COI / W-9 / BMC-91
- 68. Nova driver support — inbound chat & SMS routing into Supabase threads
- 69. Signal / Echo — outbound & inbound unified inbox
- 70. Atlas / Beacon / Orbit / Pulse — routing, alerting, lifecycle, KPIs

## Phase 5B — Auth, billing, compliance (71–80)
- 71. Supabase Auth on all `/api/*` routes (service-role → JWT)
- 72. Role matrix: carrier_admin, dispatcher, driver, internal_ops
- 73. Stripe plan enforcement middleware (feature gates by tier)
- 74. Webhook hardening — Stripe + Motive + Vapi signed payloads
- 75. Audit log table + immutable append writer
- 76. PII encryption at rest for bank / ELD credentials
- 77. Founders claim flow — idempotent reserve → pay → convert
- 78. e-Sign PDF storage in Supabase Storage + hash into `signatures_audit`
- 79. Privacy / TOS / data-retention job (GDPR-style purge)
- 80. Security review pass against `.claude` security-review skill

## Phase 5C — Background jobs + integrations (81–90)
- 81. Task queue (RQ or Celery) + worker Dockerfile
- 82. Scheduled jobs: FMCSA sync, COI expiry scan, nurture cadence, daily digest
- 83. Motive ELD live webhook → `truck_telemetry` + HOS
- 84. Samsara / Geotab / Omnitracs adapters behind one `eld_provider` interface
- 85. Google Maps directions + ETA cache
- 86. Twilio SMS (outbound + STOP + delivery receipts)
- 87. Vapi voice calls (outbound dial, transcript ingest)
- 88. Airtable bidirectional sync
- 89. Slack ops channel webhooks (alerts, digest, escalations)
- 90. Email: SES / Resend adapter + DKIM setup

## Phase 5D — Ops Suite polish + launch prep (91–100)
- 91. Ops Suite AI Agents page — live status, last run, next run
- 92. Ops Suite Founders page — reserve / claim / refund controls
- 93. Ops Suite Lead Pipeline — kanban + bulk actions
- 94. Ops Suite Fleet — live telemetry map (Mapbox or Google)
- 95. Ops Suite Compliance — Shield board (COI, policies, Clearinghouse)
- 96. Ops Suite Finance — Penny + Settler dashboards
- 97. Observability — structured logs, Sentry, per-agent metrics
- 98. Load tests + Supabase index tuning
- 99. Staging deploy (Fly.io or Render) + smoke tests
- 100. Production cutover checklist + on-call runbook

## Exit criteria for Stage 5
- All 14 agents execute end-to-end against Supabase with recorded runs.
- Full auth + Stripe gating across API.
- Intake wizard signs up a paying Founder in one session with no manual steps.
- Ops Suite shows live telemetry, pipeline, compliance, finance boards.
- Staging green; production runbook merged.

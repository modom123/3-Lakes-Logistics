# 08 — Next Actions

Ordered checklist to pick up Stage 5 from a cold start.

## Pre-flight
- [ ] Confirm branch `claude/api-routing-steps-FU4mU` is checked out.
- [ ] Copy `backend/.env.example` → `backend/.env`, fill Supabase,
      Stripe, Motive, Vapi, Twilio keys.
- [ ] Run SQL migrations `001`–`007` against Supabase project.
- [ ] `docker build` backend and smoke-test `/health`.

## First sprint (61–65)
1. **Step 61** — Implement `agents/router.py` task queue pull + audit log
   writer. Add `agents_runs` table migration if needed.
2. **Step 62** — Flesh out `sonny.py`: pull open loads from `lead_pipeline`
   and available trucks from `fleet_assets` + HOS, rank, write match record.
3. **Step 63** — Wire `shield.py` to a real FMCSA client; cron entry for
   nightly SAFER / Clearinghouse / COI-expiry scan.
4. **Step 64** — `scout.py` hooks into prospecting outputs → scoring →
   pipeline insert + stage transition rules.
5. **Step 65** — `penny.py` consumes Stripe webhooks, applies plan changes
   to `active_carriers.plan`, triggers dunning emails via `email_nurture`.

## Second sprint (66–70)
6. Settler weekly settlement packet (PDF) + ACH push stub.
7. Audit OCR pipeline for COI / W-9 / BMC-91.
8. Nova support inbox (Supabase `support_threads` table — add migration `008`).
9. Signal + Echo unified inbox reuse of the same threads table.
10. Atlas/Beacon/Orbit/Pulse behaviors per Phase 5A step 70.

## Git hygiene each step
- One commit per step, message format: `Stage 5 step NN: <description>`.
- Push to `claude/api-routing-steps-FU4mU` after each step; open PR to `main`
  only when a Phase (5A–5D) completes.
- Update `sessions/` summary when a Phase wraps.

## Handoff note
If a new session picks this up: read `project_summary/README.md` first, then
`07_stage5_plan.md` and this file. The current active branch already carries
the Phase-4 wiring — no catch-up rebase required.

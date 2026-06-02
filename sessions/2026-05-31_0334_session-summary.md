Filed: 2026-05-31T03:34:46Z

# Session Summary — 2026-05-31

## 1. Work Completed This Session

### Light Fleet Self-Service Signup Flow
- Rebuilt `page-lf-intake` in `website.html` — changed from "application" to self-service signup
- Added `lfStartSignup(type, label, color)` JS function — navigates to intake, pre-checks segment
- Insurance block is client-side; dirty record now caught by real MVR check (not honor system)
- Success screen: "We're checking your record" (pending screening, not instant approval)
- Form collects: license number, license state, DOB (required for MVR)

### Light Fleet AI Workers (4 agents built)
- `maya.py` — driver intake & onboarding: auto-approves via Checkr/Stripe, sends SMS
- `kai.py` — load finder: sweeps NEMT clients table, executive_accounts, Curri API, Roadie API
- `rio.py` — dispatcher: matches pending trips to active drivers, fires assignment
- `cash.py` — settlement: calculates driver/platform split (15% starter / 5% pro), logs to ledger
- All 4 wired into `router.py`

### Curri + Roadie Integrations
- `curri_client.py` — full Curri carrier API (available orders, accept, reject, status, webhooks)
- `roadie_client.py` — full Roadie API (available gigs, claim, shipments, webhooks)
- `kai.py` updated — `_find_courier_loads()` now polls Curri + Roadie live when keys set
- `routes_lf_webhooks.py` — POST /api/webhooks/curri and /api/webhooks/roadie
  - Inbound status events update trip records
  - Auto-queues new loads via Kai, auto-settles via Cash
- Outside Bond: added `lf_platform_connect` and `lf_register_webhooks` task types

### Checkr MVR Screening (to be replaced with Stripe Identity)
- `checkr_client.py` — Checkr API wrapper (candidate, report, invitation, adjudication)
- `maya.py` updated — sends Checkr invitation, sets driver pending_screening, webhook approves/denies
- `routes_checkr_webhook.py` — Checkr webhook receiver (report.completed → approve or deny)
- User discovered Checkr requires business approval (not instant) → switching to Stripe Identity

### Public Driver Intake API Endpoint
- `routes_light_fleet.py` — added `public_router` (no auth) with POST `/api/light-fleet/drivers/intake`
- Routes through Maya for instant approve/deny logic

### SQL Schema Updates
- `light_vehicle_trips` — added: external_id, source, driver_payout, platform_fee, settled_at, assigned_at, auth_logged_at
- `light_vehicle_drivers` — added: plan, checkr_candidate_id, checkr_invitation_id, checkr_report_id, checkr_package, location, clean_record, has_insurance, referral_source, notes, onboarded_at
- Added unique index on light_vehicle_trips.external_id

### Settings
- Added: CURRI_API_KEY, CURRI_WEBHOOK_SECRET, ROADIE_API_KEY, ROADIE_WEBHOOK_SECRET, CHECKR_API_KEY, CHECKR_WEBHOOK_SECRET

---

## 2. Files Touched

- `website.html` — signup form rebuilt with license/DOB fields, pending-screening success screen
- `backend/app/agents/maya.py` — full rewrite for Checkr/screening flow
- `backend/app/agents/kai.py` — Curri + Roadie live sweep
- `backend/app/agents/rio.py` — new dispatcher agent
- `backend/app/agents/cash.py` — new settlement agent
- `backend/app/agents/curri_client.py` — new
- `backend/app/agents/roadie_client.py` — new
- `backend/app/agents/checkr_client.py` — new (to be replaced/augmented with Stripe Identity)
- `backend/app/agents/router.py` — added maya, kai, rio, cash
- `backend/app/api/routes_light_fleet.py` — added public_router + intake endpoint
- `backend/app/api/routes_lf_webhooks.py` — new (Curri + Roadie webhooks)
- `backend/app/api/routes_checkr_webhook.py` — new (Checkr webhook)
- `backend/app/api/__init__.py` — wired new routers
- `backend/app/main.py` — registered new routers
- `backend/app/settings.py` — added platform API key fields
- `backend/sql/light_fleet_schema.sql` — schema additions

---

## 3. Tables / Schema Designed

### light_vehicle_trips (additions)
- external_id TEXT — Curri/Roadie order ID for webhook matching
- source TEXT — 'curri' | 'roadie' | 'internal' etc.
- driver_payout NUMERIC — after platform fee
- platform_fee NUMERIC
- settled_at TIMESTAMPTZ
- assigned_at TIMESTAMPTZ
- auth_logged_at TIMESTAMPTZ

### light_vehicle_drivers (additions)
- plan TEXT DEFAULT 'starter' — billing tier
- checkr_candidate_id, checkr_invitation_id, checkr_report_id, checkr_package
- location, clean_record, has_insurance, referral_source, notes, onboarded_at

---

## 4. Commits on main This Session

- `32bf356` — Light Fleet: self-service signup with instant auto-approval
- `2773a0a` — Add Light Fleet AI workers: Maya, Kai, Rio, Cash
- `b0879ac` — Add Curri + Roadie integrations for Light Fleet courier segment
- `8a05723` — Add Checkr MVR screening — real driver verification for Light Fleet

---

## 5. Pending Tasks

### Immediate (current work)
- Replace Checkr with **Stripe Identity** for license scan + verification
  - Stripe Identity: instant self-serve, ~$1.50/check, driver scans license on phone
  - Wire into Maya: after Stripe Identity clears → activate driver + welcome SMS
  - Add Stripe Identity webhook endpoint

### Platform Signups Needed (human action)
- Sign up at carriers.curri.com (DOT# required, 48-72h approval)
- Sign up at driver.roadie.com (3-7 day approval)
- Once approved: add CURRI_API_KEY and ROADIE_API_KEY to Render env vars
- Run Outside Bond `lf_platform_connect` to test connections
- Run Outside Bond `lf_register_webhooks` to register webhook URLs

### Database (must run in Supabase)
- `backend/sql/light_fleet_schema.sql` — NOT YET RUN — blocks all Light Fleet production use
- After Stripe Identity: add stripe_verification_session_id column to light_vehicle_drivers

### Hostinger
- Upload updated `website.html` as `index.html` on Hostinger

### NEMT (longer timeline)
- Apply to MTM / Modivcare for NEMT broker contracts (30-60 day process)
- Requires $1M–$1.5M commercial auto liability insurance
- Drivers need CPR cert + HIPAA training for NEMT segment

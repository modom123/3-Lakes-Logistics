# Session Summary — 3 Lakes Logistics

**Filed:** 2026-04-22T06:42:33Z
**Branch:** `claude/add-subscription-plans-qFsPP`
**Primary file:** `index (7).html`
**Command center:** `3LakesLogistics_OpsSuite_v5.html` (not yet wired)

---

## Work Completed (3 phases, 3 commits)

### Phase 1 — Intake form expansion (commit `1c24efa`)
Expanded the 4-step onboarding wizard in `index (7).html` into a **6-step Supabase-aligned carrier intake** capturing every field needed for 155+ automations. All input IDs match Supabase column names so `oSub()` can serialize straight to the DB.

| Step | Section | Fields |
|------|---------|--------|
| 1 | Company / Authority | `company_name`, `legal_entity`, `dot_number`, `mc_number`, `ein`, `phone`, `email`, `address`, `years_in_business` |
| 2 | Fleet Assets | `truck_id`, `vin`, `year`, `make`, `model`, `trailer_type` (Dry Van / Reefer / Flatbed / Step Deck / Box 26' / Cargo Van / Tanker-Hazmat / Hot Shot / Auto), `max_weight`, `equipment_count` |
| 3 | ELD / Telematics | `eld_provider` (Motive / Samsara / Geotab / Omnitracs), `eld_api_token`, `eld_account_id` |
| 4 | Insurance / Compliance (Shield) | `insurance_carrier`, `policy_number`, `policy_expiry`, `coi_upload`, BMC-91/MCS-90 ack, FMCSA SAFER / CSA / Clearinghouse / PSP consent |
| 5 | Banking (Settler payouts) | `bank_routing`, `bank_account`, `account_type`, `payee_name`, W-9 upload |
| 6 | Plan + e-Sign | `plan` (Stripe tier), `esign_name`, IP-stamped agreement, base64 PDF download |

### Phase 2 — Founders countdown (commit `8154786`)
Replaced the live-truck counter with a **data-driven countdown table** by truck type. One `FOUNDERS_CATEGORIES` array drives the banner pill, both counter boxes (home + services), pricing sublabel, and services headline.

### Phase 3 — Zero-state reset (commit `5636318`)
All 8 categories set to `claimed:0`. Banner reads *"All 1,000 Founders spots open — first come, first locked for life"* (`NOW OPEN`). Low-stock/running-out logic kicks in at ≤25 / ≤10 remaining.

---

## Tables Designed (Supabase schema — SQL migrations not yet created)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `active_carriers` | Master carrier record (Steps 1 + 6) | `id`, `company_name`, `legal_entity`, `dot_number`, `mc_number`, `ein`, `phone`, `email`, `address`, `years_in_business`, `plan`, `stripe_subscription_id`, `esign_name`, `esign_ip`, `esign_timestamp`, `status`, `created_at` |
| `fleet_assets` | One row per truck/trailer (Step 2) | `id`, `carrier_id` (FK), `truck_id`, `vin`, `year`, `make`, `model`, `trailer_type`, `max_weight`, `equipment_count` |
| `truck_telemetry` | Live feed from ELD | `id`, `carrier_id`, `truck_id`, `eld_provider`, `lat`, `lng`, `speed`, `heading`, `odometer`, `fuel_level`, `engine_hours`, `ts` |
| `driver_hos_status` | Hours-of-service | `id`, `carrier_id`, `driver_id`, `duty_status`, `drive_remaining`, `shift_remaining`, `cycle_remaining`, `ts` |
| `eld_connections` | Step 3 credentials (encrypted) | `id`, `carrier_id`, `eld_provider`, `eld_api_token`, `eld_account_id`, `status`, `last_sync_at` |
| `insurance_compliance` | Step 4 — Shield monitoring | `id`, `carrier_id`, `insurance_carrier`, `policy_number`, `policy_expiry`, `coi_url`, `bmc91_ack`, `mcs90_ack`, `safer_consent`, `csa_consent`, `clearinghouse_consent`, `psp_consent`, `last_checked_at` |
| `banking_accounts` | Step 5 — Settler payouts | `id`, `carrier_id`, `bank_routing`, `bank_account` (tokenized), `account_type`, `payee_name`, `w9_url`, `verified_at` |
| `lead_pipeline` | Prospecting (FMCSA / GMaps / loadboard) | `id`, `source`, `dot_number`, `mc_number`, `company_name`, `contact`, `phone`, `email`, `score`, `stage`, `owner_agent`, `last_touch_at` |
| `founders_inventory` | Drives the countdown table | `category`, `total`, `claimed`, `reserved` |
| `signatures_audit` | E-sign evidence chain | `id`, `carrier_id`, `doc_type`, `esign_name`, `ip`, `user_agent`, `pdf_hash`, `ts` |

### Founders inventory seed

| Category | Total | Claimed |
|---|---|---|
| Dry Van | 300 | 0 |
| Reefer | 200 | 0 |
| Flatbed / Step Deck | 150 | 0 |
| Box Truck 26' (Non-CDL) | 100 | 0 |
| Cargo Van | 100 | 0 |
| Tanker / Hazmat | 50 | 0 |
| Hot Shot | 50 | 0 |
| Auto | 50 | 0 |
| **TOTAL** | **1,000** | **0** |

---

## Pending — Phase 4 (60-Day plan execution)

- Read `60-Day AI Trucking Business Plan (1).pdf` and execute steps 1–60
- Scaffold `backend/` (FastAPI + Supabase) with SQL migrations for the tables above
- Wire `oSub()` → `POST /api/carriers/intake`
- Connect `3LakesLogistics_OpsSuite_v5.html` command center to backend endpoints
- Build agent stubs (Sonny, Shield, Scout, Penny, Settler, Audit, Nova, Signal, Vance, Echo, Atlas, Beacon, Orbit, Pulse) and prospecting engines

---

## Commits on branch

- `5636318` — Reset Founders countdown to 1,000 open — launch state
- `8154786` — Switch Founders counter to countdown-by-truck-type table
- `1c24efa` — Expand carrier onboarding into 6-step Supabase-aligned intake

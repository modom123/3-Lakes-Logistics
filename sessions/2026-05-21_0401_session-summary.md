Filed: 2026-05-21T04:01:05Z

# Session Summary — 2026-05-21 (continuation)

## Work Completed This Session

### 1. Service Mix & Plan Structure — Complete Rewrite
Corrected the entire plan model from incorrect 5-plan structure to the real 3-plan business model:
- **Founders** — $300/truck/month flat subscription
- **Pro** — $500/truck/month flat subscription
- **8% of Load** — 8% per-load dispatch fee, no monthly fee

### 2. Plan Helper Functions Rewritten (`eagleeye.html`)
- `normPlanKey(p)` — simplified to 3 keys: `founders`, `pro`, `pay_as_you_go`
- `planMonthly(p)` — new function: returns 300/500/0 depending on plan
- `planPct(p)` — returns 8 for pay_as_you_go, 0 for flat-fee plans
- `planShort(p)` — correct labels: "Founders $300/truck", "Pro $500/truck", "8% of Load"
- `planBadgeClass(p)` — gold/navy/blue for the 3 plans

### 3. Service Mix Card — All 3 Tracker Metrics Per Plan
Each plan now shows 3 stat boxes:
- % of total carriers on this plan
- % of total trucks on this plan
- % of total revenue (MRR for flat plans, MTD dispatch fees for 8% plan)

### 4. Revenue Breakdown Updated
- Subscription MRR progress bar = Founders + Pro combined (fleet_size × monthly rate)
- Dispatch Fees MTD = 8% plan loads only
- Dynamic goals based on active carrier count
- Outstanding AR unchanged

### 5. Add Carrier Modal — Plan Select Fixed
3 options with canonical keys: `founders`, `pro`, `pay_as_you_go`

### 6. Load Form — Dispatch % Auto-Select
- Selecting a carrier auto-sets dispatch % via `autoSetDispatchPct()`
- Founders/Pro → sets to $0 (subscription covers dispatching)
- 8% of Load → sets to 8%
- Load form options: "$0 — Subscription plan" or "8% — 8% of Load plan"

### 7. Carrier KPI Card
- "Full-Service 10%" card → renamed "8% Load Plan" counting pay_as_you_go carriers

## Files Touched
- `eagleeye.html` — plan helpers, service mix, load form, add carrier modal, KPI card

## Commits on main Branch
- `6f5ced9` — Update Eagle Eye service mix, plan keys, and dispatch auto-select
- `8196d13` — Fix plan structure to 3 real plans: Founders $300, Pro $500, 8% of Load

## Pending Tasks
- [ ] Access IEBC-MASTERHUB repo to review client outreach feature for CRM integration
- [ ] Run `backend/sql/016_fleet_multi_equipment.sql` in Supabase SQL Editor (manual step)
- [ ] Mark 5 test carriers with `is_test=true` in Supabase
- [ ] Add `STRIPE_PRICE_FOUNDERS` to Render env vars
- [ ] Add `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` to Render
- [ ] Build Founders Stripe features (welcome page, cancel/resend checkout, payment history)
- [ ] Wire Daily Checklist to `checklist_state` Supabase table
- [ ] CRM enhancements — pending masterhub client outreach review

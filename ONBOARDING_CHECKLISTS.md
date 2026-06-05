# 3 Lakes Logistics — Onboarding Checklists

> Last updated: 2026-06-05
> Owner: Operations (Eagle Eye)
> Branch: all three checklists live here — Driver, Shipper, Internal Staff

---

## Table of Contents
1. [Driver Onboarding — Light Fleet](#1-driver-onboarding--light-fleet)
2. [Shipper Onboarding](#2-shipper-onboarding)
3. [Internal Staff Onboarding](#3-internal-staff-onboarding)

---

## 1. Driver Onboarding — Light Fleet

> **Goal:** Driver is verified, active on the platform, and has completed their first load.
> **Owner:** Elena Ross (Node 202) / Victor Nash (Node 203)
> **SLA:** Complete within 48 hours of application

### Phase 1 — Application Received

- [ ] Driver submits form at `threelakeslogistics.com/light-fleet` (or referral link)
- [ ] Confirm intake email received by driver (auto-sent by Maya agent)
- [ ] Driver record created in Supabase `light_vehicle_drivers` with `status = inactive`
- [ ] Verify all required fields captured:
  - [ ] Full legal name
  - [ ] Phone (mobile — used for SMS alerts)
  - [ ] Email
  - [ ] Vehicle type (car, SUV, van, cargo van, pickup, box truck)
  - [ ] Vehicle year / make / model / plate
  - [ ] Service area (city/region)
  - [ ] Platforms opted in (3 Lakes, Roadie, GoShip, etc.)
  - [ ] Clean MVR self-attestation

### Phase 2 — License Verification

- [ ] Stripe Identity session created (check `stripe_verification_session_id` on driver row)
- [ ] Driver receives verification link via SMS/email
- [ ] Driver completes Stripe Identity flow (license scan on phone)
- [ ] Stripe webhook received: `identity.verification_session.verified`
  - If `requires_input`: driver re-notified, second attempt window open 24 hrs
  - If `canceled`: outreach call within 2 hrs; resend link if driver still interested
- [ ] `mvr_status` updated to `verified` in driver table
- [ ] If Stripe Identity unavailable (fallback path): honor-system activation, flag for manual MVR review within 7 days

### Phase 3 — Insurance & Documents

- [ ] Personal auto insurance on file (min liability limits met per state)
  - [ ] Policy number logged
  - [ ] Expiration date logged (set calendar reminder 30 days before)
- [ ] W-9 collected and filed (required for 1099 at year-end)
- [ ] Direct deposit / payment info collected
  - [ ] Bank name, routing, account
  - OR Stripe Connect link sent and completed
- [ ] Driver agreement / IC agreement signed (Adobe Sign)
  - [ ] Agreement ID logged on driver row

### Phase 4 — App & Systems Setup

- [ ] Light Fleet app installed (Android PWA from Play Store OR iOS shortcut)
- [ ] Driver can log in and see the load board
- [ ] Test push notification delivered successfully
- [ ] Driver profile complete in app:
  - [ ] Profile photo uploaded
  - [ ] Vehicle photo uploaded
  - [ ] Bio/service area confirmed

### Phase 5 — First Load

- [ ] Driver assigned and accepts first load in app
- [ ] Driver completes pickup (POD photo captured)
- [ ] Driver completes delivery (POD photo captured)
- [ ] First payment processed within pay cycle
- [ ] Post-first-load check-in call / message from ops team

### Phase 6 — Activation Sign-off

- [ ] `status` = `active` confirmed in Supabase
- [ ] Driver added to relevant Slack/WhatsApp ops channel
- [ ] Profile visible in Eagle Eye driver list
- [ ] IEBC node lead notified (Elena / Victor) — driver now in production

---

## 2. Shipper Onboarding

> **Goal:** Shipper can book loads, receive quotes, track shipments, and pay invoices without friction.
> **Owner:** Dr. James (Node 201) / Felix Grant (Node 204)
> **SLA:** Account live within 24 hours of first contact

### Phase 1 — Account Creation

- [ ] Shipper registers at `threelakeslogistics.com/shipper` or ops creates account in Eagle Eye
- [ ] Confirm registration email received (auto-sent)
- [ ] Shipper record created in `shippers` table
- [ ] Verify all required fields:
  - [ ] Company legal name
  - [ ] Primary contact name + title
  - [ ] Phone (primary)
  - [ ] Email (primary)
  - [ ] Billing address (street, city, state, ZIP)
  - [ ] EIN / Tax ID (for invoicing)

### Phase 2 — Credit & Terms

- [ ] Credit application submitted and reviewed
  - [ ] Net-15 / Net-30 / Net-45 terms assigned based on credit
  - [ ] Credit limit set
  - [ ] Terms signed via Adobe Sign (or DocuSign)
- [ ] Payment method on file:
  - [ ] ACH bank info collected, OR
  - [ ] Credit card added to Stripe customer, OR
  - [ ] Check payment address confirmed
- [ ] Invoice delivery preference set (email / portal download / both)

### Phase 3 — Shipper Portal Setup

- [ ] Shipper logs into portal at `threelakeslogistics.com/shipper`
- [ ] Profile completed:
  - [ ] Company name, address, state, ZIP confirmed
  - [ ] Billing email confirmed
- [ ] Webhook notifications configured (if shipper wants automated alerts):
  - [ ] `load.booked`
  - [ ] `load.dispatched`
  - [ ] `load.picked_up`
  - [ ] `load.delivered`
  - [ ] `load.exception`
  - [ ] `invoice.created`
- [ ] Shipper reference / PO number format agreed (for their internal PO matching)

### Phase 4 — First Shipment Walkthrough

- [ ] Ops or sales walks shipper through the New Shipment Wizard:
  - [ ] Step 1: Origin & Destination (addresses, contact names, phone)
  - [ ] Step 2: Pickup date/time window
  - [ ] Step 3: Commodity, weight, equipment type
  - [ ] Step 4: Accessorials (liftgate, residential, appointment, etc.)
  - [ ] Step 5: Review quote → book
- [ ] First load booked and confirmed
- [ ] Shipper can see load status on portal dashboard
- [ ] Tracking link shared (public `track.html` page) for their visibility
- [ ] First invoice generated and delivered correctly

### Phase 5 — Ongoing Relationship Setup

- [ ] Shipper added to CRM in Eagle Eye (company, contact, tier)
- [ ] Preferred lanes / commodity types noted in CRM
- [ ] Dedicated ops contact assigned and introduced to shipper
- [ ] Recurring load schedule set up if applicable (weekly/monthly lanes)
- [ ] Eagle Eye CSO office briefed on account

### Phase 6 — Onboarding Sign-off

- [ ] First invoice paid (confirms billing loop works end-to-end)
- [ ] Shipper satisfaction check-in (call or email) at 30 days
- [ ] Account flagged as `active` / `production` in Eagle Eye
- [ ] IEBC node lead notified — shipper account live

---

## 3. Internal Staff Onboarding

> **Goal:** New team member is fully set up in all systems, understands their role, and can operate independently.
> **Owner:** Founders / Mark
> **SLA:** Day-1 access complete before first shift; full system access within 72 hours

### Phase 1 — Before Day 1

- [ ] Offer letter signed
- [ ] I-9 / right-to-work documents collected
- [ ] W-4 collected and filed
- [ ] Direct deposit info collected
- [ ] Role defined and IEBC node assigned (if applicable)
- [ ] Equipment ordered / confirmed (laptop, phone if provided)

### Phase 2 — Day 1 — Accounts Created

**Email & Communication**
- [ ] Company email created (`name@3lakeslogistics.com`)
- [ ] Added to relevant Slack / WhatsApp channels
- [ ] Introduced to team via group channel

**Core Systems Access**
- [ ] Eagle Eye (eagleeye.html) — login credentials issued
- [ ] Supabase — read access granted (role-based; most staff read-only)
- [ ] Render.com — access if engineer role
- [ ] Stripe Dashboard — access if ops/finance role
- [ ] Hostinger / cPanel — access if web/IT role
- [ ] Google Workspace (Drive, Calendar, Gmail)

**Ops Tools**
- [ ] DAT load board access (if dispatch role)
- [ ] Motive ELD portal access (if fleet ops role)
- [ ] Adobe Sign / DocuSign admin (if contracts role)
- [ ] Bland.ai / Vapi dashboard (if sales/SDR role)

### Phase 3 — Day 1 — Systems Training

- [ ] Eagle Eye walkthrough:
  - [ ] Dispatch board (loads, statuses, map)
  - [ ] Shipper CRM
  - [ ] Driver management
  - [ ] Agent nodes (IEBC) — what each agent does
  - [ ] Checklists tab — daily ops tasks
  - [ ] KPI dashboard
- [ ] Load lifecycle walkthrough:
  - [ ] Quote → Book → Dispatch → Pickup → Delivery → Invoice → Payment
- [ ] Escalation paths explained:
  - [ ] Who to call for driver no-show
  - [ ] Who to call for shipper complaint
  - [ ] Who to call for system outage
- [ ] IEBC agent assignments explained:
  - [ ] Node 201 — Dr. James (NEMT)
  - [ ] Node 202 — Elena Ross (LF Ops)
  - [ ] Node 203 — Victor Nash (LF Ops)
  - [ ] Node 204 — Felix Grant (Courier)
  - [ ] Node 205 — Morgan Hayes (LF Analytics)
  - [ ] Bond — Consultant (runs diagnostics, reporting, audits)

### Phase 4 — Role-Specific Training

**Dispatch**
- [ ] How to post loads to DAT
- [ ] How to accept/assign loads in Eagle Eye
- [ ] Check Call procedures (every 2 hrs in transit)
- [ ] Exception handling (breakdowns, late pickups, claims)

**Driver Relations**
- [ ] Light Fleet app walkthrough (driver-side view)
- [ ] How to read Stripe Identity verification status
- [ ] How to activate / suspend a driver
- [ ] Insurance expiration tracking process

**Sales / Business Development**
- [ ] Shipper portal demo (know the product before selling it)
- [ ] Quote process — how rates are calculated (haversine × 1.25 × RPM by equipment type)
- [ ] CRM in Eagle Eye — how to add/update shipper leads
- [ ] Bland.ai outbound call setup

**Finance / Invoicing**
- [ ] How invoices are generated (Atomic Ledger — internal GL)
- [ ] How to apply payments in Atomic Ledger
- [ ] Factoring setup and reconciliation process
- [ ] 1099 season — driver payment records pull from Supabase

**Engineering / IT**
- [ ] Codebase walkthrough (GitHub repo: `modom123/3-Lakes-Logistics`)
- [ ] Backend: FastAPI on Render.com — deploy process
- [ ] Database: Supabase PostgreSQL — table overview
- [ ] Frontend: static HTML/CSS/JS on Hostinger
- [ ] Webhook architecture (Stripe, Checkr, Motive, Bland, Vapi, Adobe)
- [ ] Environment variables — never commit secrets; use Render env panel
- [ ] Branch strategy: `claude/wizardly-bohr-dV9qs` is current dev branch

### Phase 5 — Security & Compliance

- [ ] Password manager account created and set up
- [ ] MFA enabled on all accounts (email, Supabase, Stripe, Render)
- [ ] Security policy reviewed and signed:
  - [ ] No sharing of API keys / Bearer tokens
  - [ ] No accessing shipper or driver PII from personal devices
  - [ ] No screenshots of financial data shared externally
- [ ] FMCSA / DOT compliance basics reviewed (if dispatch/ops role):
  - [ ] HOS rules awareness
  - [ ] USDOT #4265380 / MC #1621740 on all documentation

### Phase 6 — First Week Check-ins

- [ ] Day 3: Check-in with direct supervisor — any blockers?
- [ ] Day 7: Access audit — all needed systems working?
- [ ] Day 14: Role-specific skill check (can they operate independently?)
- [ ] Day 30: Full performance check-in + 90-day goals set

### Phase 7 — Sign-off

- [ ] All systems access confirmed working
- [ ] Emergency contact info collected and filed
- [ ] HR file complete (I-9, W-4, offer letter, signed policies)
- [ ] Employee added to payroll cycle
- [ ] Welcome announcement posted (internal channel)

---

## Quick Reference — System Logins

| System | URL | Who Has Access |
|---|---|---|
| Eagle Eye | `threelakeslogistics.com/eagleeye.html` | All ops staff |
| Shipper Portal | `threelakeslogistics.com/shipper` | Shipper accounts + ops |
| API Backend | `three-lakes-logistics-api.onrender.com` | Engineers |
| Supabase | `app.supabase.com` | Engineers + data roles |
| Stripe | `dashboard.stripe.com` | Finance + engineers |
| Render.com | `render.com` | Engineers |
| Hostinger | `hpanel.hostinger.com` | Engineers + web |
| DAT Load Board | `dat.com` | Dispatch |
| Motive ELD | `keeptruckin.com` | Fleet ops |
| GitHub | `github.com/modom123/3-Lakes-Logistics` | Engineers |

---

## Notes

- **Atomic Ledger** handles all GL / accounting internally — do NOT set up QuickBooks integration
- **Stripe Identity** is the driver license verification system ($1.50/verification)
- **IEBC agents** run autonomously — staff should monitor, not override, unless escalating
- All PII (driver SSN, DOB, license number) stays in Supabase and Stripe only — never in Slack, email, or spreadsheets

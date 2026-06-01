Filed: 2026-06-01T22:08:49Z

# Session Summary — 2026-06-01 (evening)

## Work Completed

### 1. 12 Internal Agreement HTML Files (all created & stored)
- `independent-contractor-agreement.html`
- `nda.html`
- `non-solicitation-agreement.html`
- `driver-lease-on-agreement.html`
- `fuel-advance-agreement.html`
- `cargo-claims-procedure.html`
- `rate-confirmation-template.html`
- `insurance-requirements.html`
- `dispatcher-service-agreement.html`
- `factoring-acknowledgment.html`
All wired into e-sign system (AGREEMENT_LABELS + AGREEMENT_PATHS in routes_agreements.py).
All appear in Eagle Eye Agreements page with View + Send buttons.

### 2. E-Sign System Expanded
- `routes_agreements.py` AGREEMENT_LABELS/PATHS expanded from 3 → 13 agreement types
- Modal select and AGR_LABELS JS dict updated to match
- POSTMARK_SERVER_TOKEN added to backend/.env (463f8816-ad4c-4f6c-9232-890c85c204a0)

### 3. Execution Engine — Agreements by Domain Panel
Added "Agreements by Execution Domain" panel to Execution Engine page:
- Onboarding: Carrier Dispatch Agreement, Driver Lease-On, Insurance Requirements, Non-Solicitation
- Dispatch: Rate Confirmation, Broker-Carrier Agreement, Cargo Claims, Fuel Advance
- Settlement: Fuel Advance, Rate Confirmation (view), Cargo Claims (view), Factoring NOA
- Compliance: Insurance Requirements, Cargo Claims, Terms of Service
- LF Onboarding: IC Agreement, Insurance Requirements
- Dispatcher/Internal: Dispatcher Service Agreement, IC Agreement, Non-Solicitation, NDA

### 4. Agreement Domain Corrections
- Removed NDA from Carrier Onboarding and LF Onboarding (belongs to internal staff only)
- Removed IC Agreement from Carrier Onboarding and LF Onboarding (belongs to internal staff)
- Both now live only in Dispatcher/Internal domain

### 5. Full Factoring Feature
**Document**: `factoring-acknowledgment.html` — NOA with UCC Article 9, payment routing, 3LL double-payment protection, carrier representations, termination requiring both parties

**Backend** (`backend/app/api/routes_factoring.py`):
- GET /api/factoring — list assignments
- POST /api/factoring — create + auto-send NOA via Postmark
- PATCH /api/factoring/{id} — update
- DELETE /api/factoring/{id} — deactivate
- POST /api/factoring/{id}/resend — resend NOA email
- GET /api/factoring/stats — KPI counts
- Registered in __init__.py and main.py

**Database** (`backend/sql/factoring_schema.sql`):
- `carrier_factoring` table: carrier info, factor company info, payment routing, NOA status tracking, audit timestamps

**Eagle Eye Factoring Page**:
- KPI strip, 8 common factor company reference cards
- Carrier assignments table with NOA status badges
- Add modal with autocomplete factor company list
- Resend NOA / Deactivate per row
- Nav sidebar under Contracts section
- Factoring NOA card added to Agreements page (13th)
- Settlement domain in Execution Engine links to Factoring page

## Files Touched
- `eagleeye.html`
- `backend/app/api/routes_agreements.py`
- `backend/app/api/routes_factoring.py` (new)
- `backend/app/api/__init__.py`
- `backend/app/main.py`
- `backend/sql/factoring_schema.sql` (new)
- `backend/.env` (POSTMARK_SERVER_TOKEN added — not committed)
- All 10 new HTML agreement files

## Commits on Branch (main)
- `893b4cb` — Wire 9 new internal agreements into e-sign system
- `d4ce5c2` — Expand agreement documents with full legal content
- `30bd831` — Attach agreements to Execution Engine by domain
- `c89850a` — Remove NDA from carrier and LF onboarding domains
- `b7c3c0a` — Move IC Agreement to Dispatcher/Internal domain
- `86d32bb` — Add full carrier factoring feature

## Pending Tasks
- **Run `backend/sql/factoring_schema.sql` in Supabase** — creates carrier_factoring table
- **Add POSTMARK_SERVER_TOKEN to Render** — `463f8816-ad4c-4f6c-9232-890c85c204a0`
- **Add email passwords to Render** — `EMAIL_*_PASSWORD=$Itspossible56`
- **Run `sql/028_mailboxes.sql` in Supabase**
- **Run `backend/sql/light_fleet_schema.sql` in Supabase**
- **Add `STRIPE_IDENTITY_WEBHOOK_SECRET` to Render**
- **Upload website.html to Hostinger as index.html**
- **Curri/Roadie API signups**
- **Add `RENDER_API_KEY`** for Technical Team auto-redeploy

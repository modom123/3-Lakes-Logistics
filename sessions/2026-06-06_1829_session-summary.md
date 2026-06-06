Filed: 2026-06-06T18:29:43Z

# Session Summary — 2026-06-06 18:29

## Work Completed

### 1. Services Page Cleanup (carried over)
- Removed duplicate "Core Services" block (360KB base64 image + generic bullet list)
- Replaced with 4 rich feature cards: AI Dispatch, Revenue Recovery, Document Processing, 24/7 Dispatch
- Applied to both `website.html` AND `index.html` (Falcon — served at Vercel root)

### 2. Admin Link 404 Fix
- `vercel.json`: removed `buildCommand`/`outputDirectory` (was requiring `npm run build`)
- Added explicit `/admin → /eagleeye.html` and `/eagleeye → /eagleeye.html` routes
- Updated admin nav links in both HTML files from `href="/eagleeye.html"` to `href="/admin"`

### 3. Leads Section Error Fix
- `backend/sql/018_leads_columns.sql` (NEW): adds `city`, `state`, `business_name`, `status`, `dot_age_days`, `phone_number`, `equipment_type` columns + INSERT/UPDATE/DELETE RLS policies
- `backend/app/models/lead.py`: added missing fields matching the DB schema
- `backend/app/api/routes_leads.py`: fixed `stage` vs `status` filter bug; added try/except; sync both column-name variants on writes

### 4. Carrier Intake Onboarding Fix (Joel Mccool root cause)
- `backend/app/models/intake.py`: changed `company_name: str = Field(min_length=2)` → `company_name: str | None = None`; added `owner_first_name`/`owner_last_name` fields
- `backend/app/api/routes_intake.py`: added company_name fallback — if blank, uses `owner_first_name + owner_last_name`; routes welcome email using computed name
- `website.html` + `index.html`: `sendIntake()` `.catch()` now shows `#obWinErr` visible error banner instead of silent localStorage queue
- Added `<div id="obWinErr">` to obWin success screen in both files

### 5. Light Fleet Driver Intake Fix (primary blocker)
- `backend/app/agents/maya.py`: removed `platforms_opted_in` from core DB insert (column doesn't exist in schema → silent failure → driver never created); added post-insert update with graceful catch so it works without schema change
- `backend/sql/019_lf_driver_additions.sql` (NEW): migration to add `platforms_opted_in`, `dob`, `activated_at` columns (manual run needed for full feature, not required for core onboarding)

### 6. Eagle Eye "Add Carrier" Button Fix
- `backend/app/api/routes_carriers.py`: added `POST /api/carriers/` endpoint (uses service role key, bypasses RLS)
- `eagleeye.html`: `saveCarrier()` rewritten to call API instead of direct Supabase (was blocked by `no_client_inserts_carriers` RLS policy — all manual carrier additions silently failed)

## Files Touched
- `website.html`
- `index.html`
- `vercel.json`
- `eagleeye.html`
- `backend/app/models/intake.py`
- `backend/app/models/lead.py`
- `backend/app/api/routes_intake.py`
- `backend/app/api/routes_leads.py`
- `backend/app/api/routes_carriers.py`
- `backend/app/agents/maya.py`
- `backend/sql/018_leads_columns.sql` (new)
- `backend/sql/019_lf_driver_additions.sql` (new)

## Commits on main Branch
```
6d6d5f2  Fix light fleet driver intake: remove platforms_opted_in from core insert
963569a  Fix Eagle Eye Add Carrier + add POST /api/carriers/ endpoint
b072bf2  Fix carrier & light-fleet onboarding failures
201fd8c  Fix leads section error: add missing columns, fix stage/status mismatch
1576063  Apply Heavy Fleet page cleanup to index.html (Falcon)
769e5d5  Fix Admin link 404: route /admin to Eagle Eye, serve from repo root
```

## Pending Tasks

### CRITICAL — SQL migrations must be run in Supabase SQL Editor
1. **Migration 018** (`backend/sql/018_leads_columns.sql`): adds missing columns to `leads` table — needed for Eagle Eye Leads section to work
2. **Migration 019** (`backend/sql/019_lf_driver_additions.sql`): adds `platforms_opted_in`, `dob`, `activated_at` to `light_vehicle_drivers` — NOT required for core onboarding (already fixed in code), but needed to store platform preferences

### IN PROGRESS
- Render must redeploy to pick up latest code fixes (auto-deploy on push, or trigger via Bond Office → render_restart)
- Testing light fleet driver intake for Joel Mccool end-to-end

### Environment Limitation
- This container's network policy blocks all outbound HTTP (Supabase, Render API, Vercel, external domains all return "Host not in allowlist")
- Cannot directly call live APIs, open browser, or test live site from this environment
- Tests must be run from user's browser console or Eagle Eye

## Known Architecture Notes
- `no_client_inserts_carriers` RLS policy blocks all Supabase anon-key inserts to `active_carriers` — Add Carrier button now routes through API (fixed)
- `light_vehicle_drivers` vehicle_type CHECK: `('suv','sedan','cargo_van','luxury')` — form options match
- `sendIntake()` in carrier form: fire-and-forget, success screen shown before API responds — error banner added to inform user of failures
- Maya agent: if Stripe key configured → creates Stripe Identity verification session; if not → honor-system approval (driver set to active if clean_record=yes)

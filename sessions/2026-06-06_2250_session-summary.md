Filed: 2026-06-06T22:50:21Z

# Session Summary — Light Fleet / Eagle Eye redesign, audit & deploy diagnosis

## 1. Work completed since last summary

### Eagle Eye UI work (eagleeye.html)
- Renamed left-nav "Main" → "Heavy Fleet"; reordered nav so Heavy Fleet + Light Fleet sit at top (below Command); moved North American Trading to bottom.
- Added "Recently Onboarded — Light Fleet" widget to the dashboard.
- Redesigned all 4 IEBC Light Fleet pages (NEMT, Medical, Executive, Courier):
  - Iterated two-column layout → rejected → replaced with a horizontal driver
    **roster strip** (`.lf-roster-strip` / `.lf-driver-chip`) + full-width ops.
  - Removed all two-column CSS/HTML (`.lf-two-col`, `.lf-col-*`, `.lf-roster-tbl`).
- IEBC audit fixes: corrected KPI element IDs (exec/courier/gig), added the
  missing `medical` branches to lfLoadKpis/lfLoadTrips, fixed typeKey medical→med.

### Full audit (two subagents) + fixes
- **Backend onboarding audit** + **frontend LF audit** completed.
- Fixed (commit f25422c):
  - lfRunExpert: now routes through lfFetch (correct API origin + admin token)
    instead of a relative fetch that hit the static host → "Agent unavailable".
  - lfLoadRoster: dropped bogus `eagle-eye-staff` fallback token (403) → uses
    lfFetch; fixes "Error loading roster".
  - approved_services now defaults from vehicle_type (luxury→executive,
    else→courier) in BOTH create_driver and maya intake → drivers no longer
    invisible on every roster.
  - live-locations: `full_name` (nonexistent column) → `name`.

### Deploy diagnosis (root cause of "I don't see changes")
- Architecture clarified by user:
  - website.html = PUBLIC site → Hostinger (FTP)
  - eagleeye.html = INTERNAL command center → Vercel
  - Render = backend AI agents API (three-lakes-logistics-api.onrender.com)
- Found Hostinger website deploy has **failed on every run**:
  1. `SamKirkland/FTP-Deploy-Action@4.3.4` (nonexistent tag) → fixed to @v4.4.0.
  2. After fix, fails with `Input required and not supplied: server` — the FTP
     secrets (HOSTINGER_FTP_HOST/USER/PASSWORD) are NOT set. User must add them.
- Railway backend deploy also fails every run (empty RAILWAY_TOKEN) — but the
  frontend actually calls Render, so Railway workflow may be defunct.
- vercel.json: added no-cache/must-revalidate header (commit 4c6f31d) so the
  internal command center always revalidates.
- deploy-hostinger.yml: now excludes eagleeye.html from the public deploy.

## 2. Files touched
- eagleeye.html (nav, dashboard widget, LF page redesign, JS auth fixes)
- backend/app/api/routes_light_fleet.py (?service= filter, _default_services,
  full_name→name)
- backend/app/agents/maya.py (approved_services default)
- vercel.json (no-cache header)
- .github/workflows/deploy-hostinger.yml (action version, exclude eagleeye)

## 3. Tables / schemas
- No schema changes. Relevant table: public.light_vehicle_drivers
  (approved_services text[] is the segment filter key).

## 4. Commits on main (this session)
- 0663cd3 nav reorder, rosters, dashboard widget
- fad52b1 two-column layout + McCool/Courier service filter (backend ?service=)
- 1eeabda IEBC audit UI fixes
- f85eab0 IEBC redesign: roster strip layout, roster auth fix, CSS cleanup
- f25422c deploy blocker (FTP action ver) + LF onboarding/page audit fixes
- 4c6f31d vercel no-cache + keep eagleeye off public Hostinger site

## 5. Pending tasks
- USER must add 3 GitHub secrets for Hostinger public-site auto-deploy:
  HOSTINGER_FTP_HOST, HOSTINGER_FTP_USER, HOSTINGER_FTP_PASSWORD (from Hostinger
  hPanel → Files → FTP Accounts). I cannot retrieve these or set secrets.
- Decide whether to keep/remove broken Railway workflow (frontend uses Render).
- Optional backend onboarding hardening flagged in audit but NOT yet done:
  Stripe-path drivers may never activate (C1); step engine overrides status &
  ignores requires_steps (C2/C3); Checkr auto-denies "consider" (M4).
- Verify Vercel project is connected to auto-deploy from GitHub main.

# 01 — Overview

## What is being built
3 Lakes Logistics: a subscription-based AI-run trucking operations platform.
Public marketing + 6-step carrier onboarding on one side, internal Ops Suite
command center on the other, both backed by a FastAPI + Supabase service that
dispatches work across 14 named AI agents and 20 prospecting engines.

## Stack
- **Frontend (public):** `index (7).html` — landing, Founders countdown, 6-step
  Supabase-aligned carrier intake wizard, Stripe plan picker, e-sign.
- **Frontend (internal):** `3LakesLogistics_OpsSuite_v5.html` — command center
  with AI Agents, Founders Program, Lead Pipeline pages wired through a
  bearer-token API wrapper.
- **Backend:** FastAPI (`backend/app`) + Supabase (Postgres + RLS) + Stripe.
- **AI:** Claude-based agent modules with shared `agents/prompts.py` + router.
- **Runtime:** Dockerfile in `backend/`; Supabase migrations in `backend/sql`.

## Repo layout (post Phase 4)
```
backend/
  Dockerfile
  README.md
  requirements.txt
  .env.example
  app/
    main.py                 # FastAPI entrypoint
    settings.py
    supabase_client.py
    logging_service.py
    agents/                 # 14 agents + router + prompts
    api/                    # 9 route modules
    models/                 # pydantic models
    prospecting/            # 20 prospecting engines
  scripts/
    init_stripe_product.py
    seed_demo_data.py
  sql/
    001_active_carriers.sql ... 007_rls_policies.sql
index (7).html               # public site
3LakesLogistics_OpsSuite_v5.html  # command center
sessions/                    # running session summaries
project_summary/             # THIS folder
```

## Progress markers
- **60-Day Business Plan:** steps 1–60 complete (Phase 4 commit `037dae4`).
- **Stage 5 (steps 61–100):** not started — see `07_stage5_plan.md`.

## Reference commits
| SHA | Meaning |
|-----|---------|
| `1c24efa` | 6-step Supabase-aligned carrier intake |
| `8154786` | Founders countdown-by-truck-type |
| `5636318` | Zero-state reset: 1,000 spots open |
| `037dae4` | Phase 4 — FastAPI backend + wiring (steps 1–60) |
| `4e53803` | Post-Phase-4 upload (latest on `main`) |

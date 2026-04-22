# 3 Lakes Logistics — Backend

FastAPI + Supabase backend wired to the **index (7).html** public site
and the **3LakesLogistics_OpsSuite_v5.html** command center.
Executes Phases 1–3 (steps 1–60) of `Logistics Hub Implementation Roadmap.pdf`.

## Layout

```
backend/
├── requirements.txt
├── Dockerfile
├── .env.example
├── sql/                       # steps 5-9 migrations
│   ├── 001_active_carriers.sql
│   ├── 002_fleet_assets.sql
│   ├── 003_truck_telemetry.sql
│   ├── 004_leads.sql
│   ├── 005_driver_hos_status.sql
│   ├── 006_banking_and_compliance.sql
│   └── 007_rls_policies.sql
├── app/
│   ├── main.py                # FastAPI entrypoint
│   ├── settings.py            # pydantic-settings
│   ├── supabase_client.py     # step 14
│   ├── logging_service.py     # step 16 (writes agent_log)
│   ├── models/                # Pydantic schemas
│   ├── api/                   # route groups
│   │   ├── routes_intake.py       ← POST /api/carriers/intake (the 6-step form)
│   │   ├── routes_carriers.py
│   │   ├── routes_fleet.py
│   │   ├── routes_telemetry.py
│   │   ├── routes_leads.py
│   │   ├── routes_dashboard.py
│   │   ├── routes_founders.py
│   │   ├── routes_agents.py       ← POST /api/agents/{name}/run
│   │   └── routes_webhooks.py     ← Stripe, Vapi, Motive
│   ├── agents/                # Phase 2 (steps 21-40)
│   │   ├── router.py, prompts.py
│   │   ├── vance.py sonny.py shield.py scout.py penny.py settler.py
│   │   │   audit.py nova.py signal.py echo.py atlas.py beacon.py
│   │   │   orbit.py pulse.py motive_webhook.py
│   └── prospecting/           # Phase 3 (steps 41-60)
│       ├── fmcsa_scraper.py (41), gmaps_scraper.py (42),
│       ├── loadboard_scraper.py (43), scoring.py (44), dedupe.py (45),
│       ├── traffic_controller.py (46), vapi_outbound.py (47),
│       ├── sms_compliance.py (48), ab_testing.py (49),
│       ├── email_nurture.py (50), url_tracking.py (51),
│       ├── dashboard.py (52), airtable_sync.py (53),
│       ├── social_listener.py (54), referral_loop.py (55),
│       ├── daily_digest.py (56), truckpaper_scraper.py (57),
│       ├── owner_search.py (58), outbound_schedule.py (59),
│       └── dry_run.py (60)
└── scripts/
    ├── init_stripe_product.py    # step 17
    └── seed_demo_data.py
```

## Quickstart

```bash
# 1. Create venv
cd backend
python -m venv .venv && source .venv/bin/activate

# 2. Install deps
pip install -r requirements.txt

# 3. Copy env + fill in keys
cp .env.example .env

# 4. Run SQL migrations in your Supabase dashboard (sql/001..007)

# 5. Start API
uvicorn app.main:app --reload --port 8080

# 6. Smoke test
curl http://localhost:8080/api/health
curl http://localhost:8080/api/founders/inventory
```

## Key endpoints

| Method | Path                           | Caller                       |
|--------|--------------------------------|------------------------------|
| POST   | `/api/carriers/intake`         | `index (7).html` `oSub()`    |
| GET    | `/api/founders/inventory`      | countdown on public site     |
| GET    | `/api/dashboard/kpis`          | command center home          |
| GET    | `/api/carriers/`               | command center `Carriers`    |
| GET    | `/api/fleet/`                  | command center `Dispatch`    |
| GET    | `/api/telemetry/latest`        | command center live map      |
| GET    | `/api/leads/`                  | command center `Leads`       |
| POST   | `/api/agents/{agent}/run`      | command center action buttons|
| POST   | `/api/webhooks/stripe`         | Stripe                       |
| POST   | `/api/webhooks/vapi`           | Vapi.ai                      |
| POST   | `/api/webhooks/motive`         | Motive / Samsara             |

Admin routes (everything except `/intake` and `/founders/inventory`)
require `Authorization: Bearer $API_BEARER_TOKEN`.

## Roadmap coverage

- **Phase 1 (1-20)** — ✅ Repo, venv-ready, deps, SQL for 5 tables + RLS, `.env`,
  `models/`, `scripts/`, `api/`, `supabase_client`, Docker, `logging_service`,
  Stripe init, Postmark/Twilio/Vapi wiring in settings.
- **Phase 2 (21-40)** — ✅ All 14 agent modules + prompts + router.
  Stub implementations with TODO markers for SDK calls.
- **Phase 3 (41-60)** — ✅ All 20 prospecting modules scaffolded.
- **Phase 4 (61-80)** — client site (`index (7).html`) already covers the
  6-step intake, Founders countdown, PWA-ready single-page design.
  Dedicated driver PWA still pending.
- **Phase 5 (81-100)** — pending.

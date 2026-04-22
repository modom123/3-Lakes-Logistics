# 04 — API Routes

All live under `backend/app/api/`. Registered in `backend/app/main.py`.
Bearer-token auth lives in `backend/app/api/deps.py`.

| Module | Surface | Primary use |
|--------|---------|-------------|
| `routes_carriers.py` | `POST /api/carriers/intake`, `GET /api/carriers/{id}`, list/update | Receives the 6-step wizard payload from `index (7).html` |
| `routes_intake.py` | `POST /api/intake/*` helpers (upload COI, W-9, etc.) | Multipart uploads tied to carrier id |
| `routes_fleet.py` | `GET/POST /api/fleet` | `fleet_assets` CRUD for the Ops Suite |
| `routes_telemetry.py` | `POST /api/telemetry/ingest`, `GET /api/telemetry` | ELD feed in + command-center reads |
| `routes_founders.py` | `GET /api/founders/inventory`, `POST /api/founders/claim` | Powers public countdown + reserve flow |
| `routes_leads.py` | `GET/POST /api/leads`, stage transitions | Pipeline surfaced in command center |
| `routes_agents.py` | `POST /api/agents/run`, `GET /api/agents/status` | Dispatches to `agents/router.py` |
| `routes_dashboard.py` | `GET /api/dashboard/*` | Aggregations for Ops Suite widgets |
| `routes_webhooks.py` | Stripe, Motive (ELD), Vapi callbacks | External inbound events |

## Front-end wiring (already in place)
- `index (7).html` — `oSub()` POSTs to `/api/carriers/intake`; counter sync
  reads `/api/founders/inventory`; localStorage queue on offline.
- `3LakesLogistics_OpsSuite_v5.html` — bearer-token API wrapper feeds the
  AI Agents, Founders Program, and Lead Pipeline pages.

# 3 Lakes Logistics — Backend

FastAPI + Supabase backend powering:
- **Public site** (`index (7).html`) — 6-step carrier intake + Founders
  countdown.
- **Command center** (`3LakesLogistics_OpsSuite_v5.html`) — AI agents,
  pipeline, fleet, compliance, finance.

Executes the full 100-step Logistics Hub Implementation Roadmap
(Stages 1–5).

## Layout

```
backend/
├── requirements.txt
├── Dockerfile               # multi-mode: api | worker | scheduler
├── docker-compose.yml       # spins up all three locally
├── .env.example
├── sql/                     # numbered migrations (run in order)
│   ├── 001_active_carriers.sql ...
│   ├── 007_rls_policies.sql
│   ├── 008_stage5_queue_and_events.sql
│   ├── 009_audit_log.sql
│   ├── 010_founders_reservations.sql
│   ├── 011_encrypted_columns.sql
│   └── 012_sms_nurture.sql
├── app/
│   ├── main.py              # FastAPI entrypoint + lifespan (Sentry, scheduler)
│   ├── worker.py            # python -m app.worker
│   ├── scheduler.py         # python -m app.scheduler
│   ├── settings.py
│   ├── security.py          # Fernet PII + webhook signature verifiers
│   ├── audit.py             # immutable audit log writer
│   ├── storage.py           # Supabase Storage uploads (agreements)
│   ├── supabase_client.py
│   ├── logging_service.py
│   ├── models/
│   ├── api/                 # route groups (all JWT- or bearer-guarded)
│   ├── agents/              # 14 agents + router + prompts + task queue
│   ├── integrations/        # eld, maps, sms, email, slack, fmcsa, stripe
│   └── prospecting/         # 20 prospecting modules
└── scripts/
    ├── init_stripe_product.py
    └── seed_demo_data.py
```

## Quickstart

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # fill keys
# Run SQL migrations in Supabase (sql/001 → sql/012)
uvicorn app.main:app --reload --port 8080
# second shell — background worker
python -m app.worker
# third shell — scheduled jobs (optional; also wired into FastAPI lifespan
# when ENABLE_SCHEDULER=1)
python -m app.scheduler
```

Smoke:
```bash
curl http://localhost:8080/api/health
curl http://localhost:8080/api/ready
curl http://localhost:8080/api/founders/inventory
```

## Auth

| Surface                                | Guard           |
|----------------------------------------|-----------------|
| Public (intake, founders inventory)    | none            |
| Command center + internal scripts      | `API_BEARER_TOKEN` via `require_bearer` |
| Carrier / dispatcher portal            | Supabase JWT via `require_jwt` + `require_role(...)` |
| Plan-gated endpoints                   | `require_plan("pro" \| "scale")` |

Use `Authorization: Bearer <token>` on every request.

## Agents

All agents support `POST /api/agents/{agent}/run` with a JSON body like
`{"kind": "match_all_trucks"}`. Synchronous responses return the result;
use the `/api/agents/log` endpoint to inspect recent runs.

Agents can also be queued for background execution:
```python
from app.agents.router import enqueue
enqueue("sonny", "match_all_trucks", {"carrier_id": "..."})
```

## Scheduled jobs

See `app/scheduler.py` for the cron table. Heartbeats land in the
`scheduled_jobs` table (visible in the Ops Suite KPI strip).

## Observability

- **Sentry** — set `SENTRY_DSN` (initialized inside lifespan).
- **KPI snapshots** — `pulse.kpi_snapshot` runs every 5 min.
- **Audit log** — every mutation writes to `audit_log` (append-only).
- **Webhook log** — every inbound signed payload lands in `webhook_log`.

## Deployment

Three services from one image via `RUN_MODE` env var:
- `RUN_MODE=api` → uvicorn on :8080 (Fly/Render/Cloud Run)
- `RUN_MODE=worker` → `python -m app.worker` (dedicated machine type)
- `RUN_MODE=scheduler` → `python -m app.scheduler` (singleton)

**Primary deploy target: Fly.io.** See `docs/DEPLOY_FLY.md` for the full
first-time launch (fly.toml + secrets + migrations + domain + vendor
webhook registration). See `docs/RUNBOOK.md` for day-2 ops and cutover.

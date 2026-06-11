# Bond Office — Autonomous DevOps (Migrations + Redeploy)

The James Bond office can now apply Supabase SQL migrations **and** trigger
Render redeploys on its own — no more manual trips to the Supabase SQL editor or
the Render dashboard.

## What it does

- Discovers repo migrations (`sql/*.sql` + `backend/sql/*.sql`).
- Applies the ones not yet in the `schema_migrations_bond` ledger (idempotent,
  checksum-tracked), in order, over a **direct Postgres connection** (no
  arbitrary-SQL RPC is installed — nothing left on the DB to abuse).
- Triggers a Render redeploy (skipped automatically if a migration failed).
- Logs every run to `bond_deploy_log`, posts a summary into the Bond channel,
  and escalates to Mark Odom + CC Gulley on failure.

## How to run it

**From the app / API** (Eagle Eye Bond Office tab, bearer auth):

| Method | Endpoint | Action |
|--------|----------|--------|
| POST | `/api/bond/deploy` | apply pending migrations **then** redeploy |
| POST | `/api/bond/migrate` | apply pending migrations only |
| POST | `/api/bond/redeploy` | redeploy only |
| GET  | `/api/bond/deploy-status` | pending list + last deploy log |

Also via the agent runner: `POST /api/agents/bond_devops/run` with
`{"action": "sync" | "migrate" | "redeploy" | "status" | "baseline"}`, and
through Outside Bond tasks `apply_sql` / `deploy_sync` (Bond's audits auto-route
"missing table / does not exist / migration" gaps here).

**From CI** — run the **"Bond — Apply Migrations & Redeploy"** GitHub workflow
(`.github/workflows/bond-deploy.yml`, `workflow_dispatch`).

## One-time setup (required for autonomy)

Set these secrets (Render env vars + GitHub repo secrets):

- `DATABASE_URL` (or `SUPABASE_DB_URL`) — Supabase → Project Settings → Database
  → Connection string (**Session pooler / URI**). This is the credential
  bond_devops uses to apply DDL. Without it, `migrate` returns a clear
  "credential not configured" message instead of guessing.
- `RENDER_API_KEY` — already used by the existing Bond Render sync; needed for
  the redeploy step.
- `API_BEARER_TOKEN` — already set; the CI helper and Bond endpoints use it.

## Already done

The live database was brought in sync as part of landing this:

- Created previously-missing tables the code depended on: `office_state`,
  `executive_escalations`, `scheduled_tasks`, plus the `schema_migrations_bond`
  ledger and `bond_deploy_log`.
- Added the `last_contact_at` / `outreach_channel` lead CRM columns.
- Baselined the ledger (all 52 repo migrations marked applied), so the runner
  only applies **new** files from here on.

> Note: no `exec_sql` / arbitrary-SQL function exists on the database. Migrations
> run over a normal Postgres connection from trusted contexts only.

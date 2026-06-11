-- 023 · Bond Office DevOps — migration ledger + deploy audit log
-- Bootstraps the James Bond office so it can apply SQL migrations and trigger
-- Render redeploys without a human visiting the Supabase SQL editor or the
-- Render dashboard. Idempotent / safe to re-run.
--
-- SQL is applied by bond_devops over a direct Postgres connection (DATABASE_URL
-- / SUPABASE_DB_URL secret), NOT via a persistent arbitrary-SQL function — so
-- there is no exec_sql RPC / RCE surface left on the database.

-- Ledger of which repo migration files the Bond office has already applied.
create table if not exists public.schema_migrations_bond (
  filename    text primary key,
  checksum    text not null,
  status      text not null default 'applied',   -- applied | failed
  error       text,
  applied_by  text not null default 'bond_devops',
  applied_at  timestamptz not null default now()
);

-- Audit log of every Bond deploy run (migrate + redeploy).
create table if not exists public.bond_deploy_log (
  id          uuid primary key default gen_random_uuid(),
  action      text not null,                      -- sync | migrate | redeploy
  applied     jsonb not null default '[]'::jsonb,
  failed      jsonb not null default '[]'::jsonb,
  redeploy    jsonb,
  ok          boolean not null default true,
  summary     text,
  created_at  timestamptz not null default now()
);

alter table public.schema_migrations_bond enable row level security;
alter table public.bond_deploy_log         enable row level security;
drop policy if exists smb_service on public.schema_migrations_bond;
drop policy if exists bdl_service on public.bond_deploy_log;
create policy smb_service on public.schema_migrations_bond using (true) with check (true);
create policy bdl_service on public.bond_deploy_log         using (true) with check (true);

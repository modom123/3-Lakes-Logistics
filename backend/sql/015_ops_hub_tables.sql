-- 015: Ops Hub compatibility tables and column additions.
-- The command center (3LakesLogistics_OpsSuite_v5.html) manages carriers,
-- loads, invoices, and notes directly via the Supabase JS client. This
-- migration provides the exact schema those queries expect.

-- ── 1. Ops Hub carrier roster ─────────────────────────────────────────────
-- Lightweight dispatch-level records added by the dispatcher in the UI.
-- Separate from active_carriers (full intake/Stripe/e-sign pipeline).
create table if not exists public.carriers (
  id                  uuid primary key default gen_random_uuid(),
  full_name           text not null,
  first_name          text,
  last_name           text,
  mc_number           text,
  dot_number          text,
  home_base           text,
  equipment           text default 'Dry Van',
  plan                text default '5% Standard',
  phone               text,
  email               text,
  insurance_provider  text,
  eld                 text,
  status              text not null default 'New — Pending Onboarding',
  enrolled_date       date default current_date,
  loads_completed     int default 0,
  created_at          timestamptz not null default now()
);

create index if not exists idx_carriers_status   on public.carriers(status);
create index if not exists idx_carriers_created  on public.carriers(created_at desc);

-- ── 2. Loads — add columns used by the ops hub dispatch board ─────────────
-- The existing loads table tracks normalized origin_city/origin_state etc.
-- The ops hub writes flat human-readable fields; add them alongside.
alter table public.loads add column if not exists driver_name   text;
alter table public.loads add column if not exists origin        text;
alter table public.loads add column if not exists destination   text;
alter table public.loads add column if not exists rate          numeric(10,2);
alter table public.loads add column if not exists rpm           numeric(6,2);
alter table public.loads add column if not exists dispatch_fee  numeric(10,2);
alter table public.loads add column if not exists dispatch_pct  numeric(5,2);
alter table public.loads add column if not exists pickup_date   date;
alter table public.loads add column if not exists commodity     text;
alter table public.loads add column if not exists notes         text;

-- ── 3. Invoices — add columns used by the ops hub billing page ────────────
alter table public.invoices add column if not exists notes      text;
alter table public.invoices add column if not exists paid_date  date;

-- ── 4. Dispatcher notes ───────────────────────────────────────────────────
create table if not exists public.dispatcher_notes (
  id          uuid primary key default gen_random_uuid(),
  title       text not null,
  body        text,
  category    text default 'General',
  created_at  timestamptz not null default now()
);

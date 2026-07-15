-- 025_stripe_connect_payouts.sql
-- Stripe Connect (Express) payout accounts for drivers + the payout ledger tables.
--
-- Closes the "onboarded but can't be paid" loophole: driver rows gain the
-- stripe_account_* columns that the payout code (routes_payout.py,
-- routes_light_fleet.py instant-pay + weekly batch, lf_settlement.py) already
-- reads/writes but that were never actually created, and the two payout ledger
-- tables (driver_payouts / lf_driver_payouts) are defined to match those inserts.
--
-- Idempotent: safe to run more than once.

-- ── Driver payout-account columns (both fleets) ──────────────────────────────
alter table if exists public.light_vehicle_drivers
  add column if not exists stripe_account_id      text,
  add column if not exists stripe_account_status  text default 'not_connected',  -- not_connected | pending | connected | restricted
  add column if not exists stripe_payouts_enabled boolean default false,
  add column if not exists stripe_onboarded_at     timestamptz;

alter table if exists public.drivers
  add column if not exists stripe_account_id      text,
  add column if not exists stripe_account_status  text default 'not_connected',
  add column if not exists stripe_payouts_enabled boolean default false,
  add column if not exists stripe_onboarded_at     timestamptz;

create index if not exists idx_lvd_stripe_account on public.light_vehicle_drivers (stripe_account_id);
create index if not exists idx_drivers_stripe_account on public.drivers (stripe_account_id);

-- ── Light-fleet payout ledger ────────────────────────────────────────────────
-- Matches inserts in lf_settlement.h262_ach_initiation, routes_light_fleet
-- instant-pay + weekly-batch, and routes_driver reads.
create table if not exists public.lf_driver_payouts (
  id                  uuid primary key default gen_random_uuid(),
  driver_id           uuid,
  trip_id             uuid,
  payout_type         text default 'weekly',              -- weekly | instant
  gross_cents         integer not null default 0,
  platform_fee_cents  integer not null default 0,
  instant_fee_cents   integer not null default 0,
  net_cents           integer not null default 0,
  status              text not null default 'queued',     -- queued | processing | paid | failed
  stripe_transfer_id  text,
  stripe_payout_id    text,
  failure_reason      text,
  requested_at        timestamptz not null default now(),
  processed_at        timestamptz,
  paid_at             timestamptz
);
create index if not exists idx_lf_payouts_driver on public.lf_driver_payouts (driver_id);
create index if not exists idx_lf_payouts_status on public.lf_driver_payouts (status);

-- ── Heavy-fleet payout ledger ────────────────────────────────────────────────
-- Matches inserts/reads in routes_payout.request_payout + get_payout_history.
create table if not exists public.driver_payouts (
  id                  uuid primary key default gen_random_uuid(),
  driver_id           uuid,
  load_id             uuid,
  amount_cents        integer not null default 0,         -- gross
  dispatch_fee_cents  integer not null default 0,
  insurance_cents     integer not null default 0,
  net_cents           integer not null default 0,
  status              text not null default 'processing', -- processing | paid | failed
  stripe_transfer_id  text,
  requested_at        timestamptz not null default now(),
  paid_at             timestamptz
);
create index if not exists idx_driver_payouts_driver on public.driver_payouts (driver_id);
create index if not exists idx_driver_payouts_status on public.driver_payouts (status);

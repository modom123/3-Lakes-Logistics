-- CLM Domain supporting tables for execution engine steps 121-150

-- Add CLM lifecycle columns to contracts
alter table contracts
  add column if not exists auto_approved       boolean not null default false,
  add column if not exists flagged_for_review  boolean not null default false,
  add column if not exists review_notes        text,
  add column if not exists archived_at         timestamptz,
  add column if not exists export_url          text,
  add column if not exists broker_agreement_id uuid references contracts(id),
  add column if not exists load_number         text,
  add column if not exists confidence_score    numeric(4,2);

create index if not exists idx_contracts_load_number  on contracts(load_number);
create index if not exists idx_contracts_flagged      on contracts(flagged_for_review) where flagged_for_review;
create index if not exists idx_contracts_archived     on contracts(archived_at) where archived_at is not null;

-- Bad-pay / blacklisted broker list
create table if not exists broker_blacklist (
  id           uuid primary key default gen_random_uuid(),
  broker_mc    text unique not null,
  broker_name  text,
  reason       text not null,
  added_by     text not null default 'system',
  added_at     timestamptz not null default now()
);

create index if not exists idx_broker_blacklist_mc on broker_blacklist(broker_mc);

-- Per-broker reliability scorecard (upserted after every settled load)
create table if not exists broker_scorecards (
  id                   uuid primary key default gen_random_uuid(),
  broker_mc            text unique not null,
  broker_name          text,
  total_loads          int not null default 0,
  avg_pay_days         numeric(5,1),
  on_time_pay_pct      numeric(5,2),
  dispute_rate_pct     numeric(5,2),
  avg_rate_per_mile    numeric(6,4),
  -- none | bronze | silver | gold | platinum
  volume_discount_tier text not null default 'none',
  last_updated_at      timestamptz not null default now()
);

create index if not exists idx_broker_scorecards_mc   on broker_scorecards(broker_mc);
create index if not exists idx_broker_scorecards_tier on broker_scorecards(volume_discount_tier);

-- Dispute records (opened at step 141, escalated at step 142)
create table if not exists clm_disputes (
  id               uuid primary key default gen_random_uuid(),
  contract_id      uuid not null references contracts(id),
  carrier_id       uuid references active_carriers(id),
  -- short_pay | no_pay | rate_variance | damage | detention_denied
  dispute_type     text not null,
  expected_amount  numeric(10,2),
  paid_amount      numeric(10,2),
  variance_amount  numeric(10,2) generated always as (expected_amount - paid_amount) stored,
  -- open | escalated | resolved | closed
  status           text not null default 'open',
  opened_at        timestamptz not null default now(),
  escalated_at     timestamptz,
  resolved_at      timestamptz,
  notes            text,
  resolution_notes text
);

create index if not exists idx_clm_disputes_contract on clm_disputes(contract_id);
create index if not exists idx_clm_disputes_carrier  on clm_disputes(carrier_id);
create index if not exists idx_clm_disputes_status   on clm_disputes(status);

-- Daily CLM analytics snapshot (upserted at step 144)
create table if not exists clm_analytics (
  id                uuid primary key default gen_random_uuid(),
  period_date       date not null unique,
  total_contracts   int not null default 0,
  total_revenue     numeric(12,2) not null default 0,
  avg_rate_per_mile numeric(6,4),
  avg_payment_days  numeric(5,1),
  dispute_count     int not null default 0,
  dispute_rate_pct  numeric(5,2),
  factored_count    int not null default 0,
  auto_approved_pct numeric(5,2),
  computed_at       timestamptz not null default now()
);

create index if not exists idx_clm_analytics_date on clm_analytics(period_date desc);

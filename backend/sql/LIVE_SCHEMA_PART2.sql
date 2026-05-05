-- ============================================================
-- 3 Lakes Logistics — LIVE SCHEMA PART 2 of 3
-- Tables: atomic_ledger, contracts, contract_events,
--         document_vault, execution_steps, driver_cdl,
--         broker_blacklist, broker_scorecards,
--         clm_disputes, clm_analytics
-- ============================================================

-- ── atomic_ledger ───────────────────────────────────────────
create table if not exists public.atomic_ledger (
  id                 uuid primary key default gen_random_uuid(),
  event_type         text not null,
  event_source       text not null,
  tenant_id          uuid,
  logistics_payload  jsonb not null default '{}',
  financial_payload  jsonb not null default '{}',
  compliance_payload jsonb not null default '{}',
  metadata           jsonb not null default '{}',
  created_at         timestamptz not null default now()
);
create index if not exists idx_al_event_type on public.atomic_ledger(event_type);
create index if not exists idx_al_created_at on public.atomic_ledger(created_at desc);
create index if not exists idx_al_tenant     on public.atomic_ledger(tenant_id);
create index if not exists idx_al_logistics  on public.atomic_ledger using gin(logistics_payload);
create index if not exists idx_al_financial  on public.atomic_ledger using gin(financial_payload);

-- ── contracts ───────────────────────────────────────────────
create table if not exists public.contracts (
  id                  uuid primary key default gen_random_uuid(),
  carrier_id          uuid references public.active_carriers(id),
  contract_type       text not null,
  status              text not null default 'draft',
  document_url        text,
  raw_text            text,
  extracted_vars      jsonb not null default '{}',
  counterparty_name   text,
  rate_total          numeric(10,2),
  rate_per_mile       numeric(6,4),
  origin_city         text,
  destination_city    text,
  pickup_date         date,
  delivery_date       date,
  payment_terms       text,
  signed_at           timestamptz,
  expires_at          timestamptz,
  milestone_pct       int not null default 0,
  invoice_id          uuid,
  gl_posted           boolean not null default false,
  revenue_recognized  boolean not null default false,
  auto_approved       boolean not null default false,
  flagged_for_review  boolean not null default false,
  review_notes        text,
  archived_at         timestamptz,
  export_url          text,
  broker_agreement_id uuid references public.contracts(id),
  load_number         text,
  confidence_score    numeric(4,2),
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
alter table public.contracts add column if not exists auto_approved       boolean not null default false;
alter table public.contracts add column if not exists flagged_for_review  boolean not null default false;
alter table public.contracts add column if not exists review_notes        text;
alter table public.contracts add column if not exists archived_at         timestamptz;
alter table public.contracts add column if not exists export_url          text;
alter table public.contracts add column if not exists broker_agreement_id uuid;
alter table public.contracts add column if not exists load_number         text;
alter table public.contracts add column if not exists confidence_score    numeric(4,2);
create index if not exists idx_contracts_carrier     on public.contracts(carrier_id);
create index if not exists idx_contracts_status      on public.contracts(status);
create index if not exists idx_contracts_type        on public.contracts(contract_type);
create index if not exists idx_contracts_pickup      on public.contracts(pickup_date);
create index if not exists idx_contracts_vars        on public.contracts using gin(extracted_vars);
create index if not exists idx_contracts_load_number on public.contracts(load_number);
create index if not exists idx_contracts_flagged     on public.contracts(flagged_for_review) where flagged_for_review;
create index if not exists idx_contracts_archived    on public.contracts(archived_at) where archived_at is not null;

-- ── contract_events ─────────────────────────────────────────
create table if not exists public.contract_events (
  id          uuid primary key default gen_random_uuid(),
  contract_id uuid not null references public.contracts(id),
  event_type  text not null,
  actor       text,
  payload     jsonb not null default '{}',
  notes       text,
  created_at  timestamptz not null default now()
);
create index if not exists idx_contract_events_contract on public.contract_events(contract_id);
create index if not exists idx_contract_events_type     on public.contract_events(event_type);

-- ── document_vault ──────────────────────────────────────────
create table if not exists public.document_vault (
  id           uuid primary key default gen_random_uuid(),
  carrier_id   uuid references public.active_carriers(id),
  contract_id  uuid references public.contracts(id),
  doc_type     text not null,
  filename     text not null,
  storage_path text not null,
  file_size_kb int,
  mime_type    text,
  scan_status  text not null default 'pending',
  scan_result  jsonb not null default '{}',
  uploaded_at  timestamptz not null default now()
);
create index if not exists idx_vault_carrier on public.document_vault(carrier_id);
create index if not exists idx_vault_type    on public.document_vault(doc_type);
create index if not exists idx_vault_scan    on public.document_vault(scan_status);

-- ── execution_steps ─────────────────────────────────────────
create table if not exists public.execution_steps (
  id             uuid primary key default gen_random_uuid(),
  step_number    int not null,
  step_name      text not null,
  domain         text not null,
  status         text not null default 'pending',
  carrier_id     uuid references public.active_carriers(id),
  contract_id    uuid references public.contracts(id),
  input_payload  jsonb not null default '{}',
  output_payload jsonb not null default '{}',
  error_message  text,
  started_at     timestamptz,
  completed_at   timestamptz,
  duration_ms    int,
  created_at     timestamptz not null default now()
);
create index if not exists idx_exec_number  on public.execution_steps(step_number);
create index if not exists idx_exec_domain  on public.execution_steps(domain);
create index if not exists idx_exec_status  on public.execution_steps(status);
create index if not exists idx_exec_carrier on public.execution_steps(carrier_id);

-- ── driver_cdl ──────────────────────────────────────────────
create table if not exists public.driver_cdl (
  id                     uuid primary key default gen_random_uuid(),
  carrier_id             uuid not null references public.active_carriers(id) on delete cascade,
  driver_id              text not null,
  driver_name            text,
  cdl_number             text,
  cdl_state              text,
  cdl_class              text,
  endorsements           text[],
  restrictions           text[],
  cdl_expiry             date not null,
  medical_card_expiry    date,
  clearinghouse_enrolled boolean default false,
  mvr_last_checked       date,
  cdl_status             text not null default 'green',
  notes                  text,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  unique (carrier_id, driver_id)
);
create index if not exists idx_cdl_carrier on public.driver_cdl(carrier_id);
create index if not exists idx_cdl_expiry  on public.driver_cdl(cdl_expiry);
create index if not exists idx_cdl_status  on public.driver_cdl(cdl_status);
create index if not exists idx_cdl_medical on public.driver_cdl(medical_card_expiry);

-- ── broker_blacklist ────────────────────────────────────────
create table if not exists public.broker_blacklist (
  id          uuid primary key default gen_random_uuid(),
  broker_mc   text unique not null,
  broker_name text,
  reason      text not null,
  added_by    text not null default 'system',
  added_at    timestamptz not null default now()
);
create index if not exists idx_blacklist_mc on public.broker_blacklist(broker_mc);

-- ── broker_scorecards ───────────────────────────────────────
create table if not exists public.broker_scorecards (
  id                   uuid primary key default gen_random_uuid(),
  broker_mc            text unique not null,
  broker_name          text,
  total_loads          int not null default 0,
  avg_pay_days         numeric(5,1),
  on_time_pay_pct      numeric(5,2),
  dispute_rate_pct     numeric(5,2),
  avg_rate_per_mile    numeric(6,4),
  volume_discount_tier text not null default 'none',
  last_updated_at      timestamptz not null default now()
);
create index if not exists idx_scorecards_mc   on public.broker_scorecards(broker_mc);
create index if not exists idx_scorecards_tier on public.broker_scorecards(volume_discount_tier);

-- ── clm_disputes ────────────────────────────────────────────
create table if not exists public.clm_disputes (
  id               uuid primary key default gen_random_uuid(),
  contract_id      uuid not null references public.contracts(id),
  carrier_id       uuid references public.active_carriers(id),
  dispute_type     text not null,
  expected_amount  numeric(10,2),
  paid_amount      numeric(10,2),
  variance_amount  numeric(10,2) generated always as (expected_amount - paid_amount) stored,
  status           text not null default 'open',
  opened_at        timestamptz not null default now(),
  escalated_at     timestamptz,
  resolved_at      timestamptz,
  notes            text,
  resolution_notes text
);
create index if not exists idx_disputes_contract on public.clm_disputes(contract_id);
create index if not exists idx_disputes_carrier  on public.clm_disputes(carrier_id);
create index if not exists idx_disputes_status   on public.clm_disputes(status);

-- ── clm_analytics ───────────────────────────────────────────
create table if not exists public.clm_analytics (
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
create index if not exists idx_clm_analytics_date on public.clm_analytics(period_date desc);

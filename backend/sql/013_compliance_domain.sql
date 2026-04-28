-- Compliance & Safety domain supporting tables for execution engine steps 151-180

-- Immutable event log for every Shield compliance action
create table if not exists shield_events (
  id           uuid primary key default gen_random_uuid(),
  carrier_id   uuid references active_carriers(id),
  -- insurance_30d | insurance_7d | insurance_expired | cdl_30d | cdl_7d |
  -- cdl_expired | csa_refresh | mc_authority_check | accident_flag |
  -- oos_rate_exceeded | safety_light_change | red_light_suspend |
  -- hazmat_missing | oversize_expired | ifta_overdue | ucr_expired |
  -- inspection_overdue | eld_missing | new_entrant_violation | mvr_due |
  -- lease_expired | escrow_deficient | compliance_score_computed
  event_type   text not null,
  -- info | warning | critical
  severity     text not null default 'info',
  payload      jsonb not null default '{}',
  resolved_at  timestamptz,
  created_at   timestamptz not null default now()
);

create index if not exists idx_shield_events_carrier  on shield_events(carrier_id);
create index if not exists idx_shield_events_type     on shield_events(event_type);
create index if not exists idx_shield_events_severity on shield_events(severity);
create index if not exists idx_shield_events_resolved on shield_events(resolved_at) where resolved_at is null;

-- Composite compliance score per carrier (upserted by step 179)
create table if not exists carrier_compliance_scores (
  id               uuid primary key default gen_random_uuid(),
  carrier_id       uuid unique not null references active_carriers(id),
  composite_score  numeric(5,2) not null default 100,  -- 0-100
  -- green | yellow | red
  safety_light     text not null default 'green',
  -- sub-scores (0-100 each, null = not yet evaluated)
  insurance_score  numeric(5,2),
  csa_score        numeric(5,2),
  cdl_score        numeric(5,2),
  ifta_score       numeric(5,2),
  ucr_score        numeric(5,2),
  inspection_score numeric(5,2),
  eld_score        numeric(5,2),
  last_computed_at timestamptz not null default now()
);

create index if not exists idx_compliance_scores_light on carrier_compliance_scores(safety_light);

-- DOT drug & alcohol testing schedule (random + triggered events)
create table if not exists drug_test_schedule (
  id           uuid primary key default gen_random_uuid(),
  carrier_id   uuid not null references active_carriers(id),
  driver_id    text not null,
  driver_name  text,
  -- random | pre_employment | post_accident | reasonable_suspicion | return_to_duty
  test_type    text not null default 'random',
  scheduled_at date not null,
  completed_at date,
  -- negative | positive | refusal | cancelled
  result       text,
  notes        text,
  created_at   timestamptz not null default now()
);

create index if not exists idx_drug_test_carrier  on drug_test_schedule(carrier_id);
create index if not exists idx_drug_test_scheduled on drug_test_schedule(scheduled_at);
create index if not exists idx_drug_test_result   on drug_test_schedule(result) where result is not null;

-- Annual vehicle inspection tracking (DOT FMCSA 49 CFR § 396.17)
create table if not exists vehicle_inspections (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid not null references active_carriers(id),
  truck_id        text not null,
  vin             text,
  last_inspection date,
  due_date        date not null,
  -- pass | fail | overdue | not_performed
  result          text not null default 'not_performed',
  defects         text[],
  sticker_expiry  date,
  notes           text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (carrier_id, truck_id)
);

create index if not exists idx_inspections_carrier  on vehicle_inspections(carrier_id);
create index if not exists idx_inspections_due      on vehicle_inspections(due_date);
create index if not exists idx_inspections_result   on vehicle_inspections(result);

-- IFTA (International Fuel Tax Agreement) quarterly filing status
create table if not exists ifta_filings (
  id           uuid primary key default gen_random_uuid(),
  carrier_id   uuid not null references active_carriers(id),
  quarter      text not null,  -- "2025-Q1"
  due_date     date not null,
  filed_date   date,
  -- pending | filed | overdue | exempt
  status       text not null default 'pending',
  created_at   timestamptz not null default now(),
  unique (carrier_id, quarter)
);

create index if not exists idx_ifta_carrier on ifta_filings(carrier_id);
create index if not exists idx_ifta_status  on ifta_filings(status);

-- UCR (Unified Carrier Registration) annual registration
create table if not exists ucr_registrations (
  id           uuid primary key default gen_random_uuid(),
  carrier_id   uuid not null references active_carriers(id),
  reg_year     int not null,
  -- pending | registered | expired
  status       text not null default 'pending',
  expiry_date  date,
  fee_paid     numeric(8,2),
  created_at   timestamptz not null default now(),
  unique (carrier_id, reg_year)
);

create index if not exists idx_ucr_carrier on ucr_registrations(carrier_id);
create index if not exists idx_ucr_year    on ucr_registrations(reg_year);

-- Annual Motor Vehicle Record (MVR) checks per driver
create table if not exists mvr_checks (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid not null references active_carriers(id),
  driver_id       text not null,
  driver_name     text,
  checked_at      date not null,
  next_due        date not null,
  -- clean | violations | suspended | revoked
  result          text,
  violation_count int not null default 0,
  notes           text,
  created_at      timestamptz not null default now()
);

create index if not exists idx_mvr_carrier  on mvr_checks(carrier_id);
create index if not exists idx_mvr_next_due on mvr_checks(next_due);

-- Owner-operator lease agreements (49 CFR § 376)
create table if not exists lease_agreements (
  id           uuid primary key default gen_random_uuid(),
  carrier_id   uuid not null references active_carriers(id),
  driver_id    text not null,
  driver_name  text,
  -- owner_operator | lease_purchase
  lease_type   text not null default 'owner_operator',
  start_date   date not null,
  end_date     date,
  auto_renew   boolean not null default true,
  -- active | expired | terminated
  status       text not null default 'active',
  document_url text,
  created_at   timestamptz not null default now(),
  unique (carrier_id, driver_id)
);

create index if not exists idx_lease_carrier on lease_agreements(carrier_id);
create index if not exists idx_lease_status  on lease_agreements(status);

-- Add compliance_suspended flag to active_carriers for step 155/164
alter table active_carriers
  add column if not exists compliance_suspended boolean not null default false,
  add column if not exists suspension_reason   text,
  add column if not exists suspended_at        timestamptz;

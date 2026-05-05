-- ============================================================
-- 3 Lakes Logistics — LIVE SCHEMA PART 3 of 3
-- Tables: shield_events, carrier_compliance_scores,
--         drug_test_schedule, vehicle_inspections,
--         ifta_filings, ucr_registrations, mvr_checks,
--         lease_agreements, analytics_daily_kpis,
--         analytics_lane_stats, analytics_driver_rankings,
--         analytics_rate_index, analytics_weekly_reports,
--         analytics_forecasts, carriers (ops hub),
--         dispatcher_notes, RLS for ops hub tables
-- ============================================================

-- ── shield_events ───────────────────────────────────────────
create table if not exists public.shield_events (
  id          uuid primary key default gen_random_uuid(),
  carrier_id  uuid references public.active_carriers(id),
  event_type  text not null,
  severity    text not null default 'info',
  payload     jsonb not null default '{}',
  resolved_at timestamptz,
  created_at  timestamptz not null default now()
);
create index if not exists idx_shield_carrier    on public.shield_events(carrier_id);
create index if not exists idx_shield_type       on public.shield_events(event_type);
create index if not exists idx_shield_severity   on public.shield_events(severity);
create index if not exists idx_shield_unresolved on public.shield_events(resolved_at) where resolved_at is null;

-- ── carrier_compliance_scores ───────────────────────────────
create table if not exists public.carrier_compliance_scores (
  id               uuid primary key default gen_random_uuid(),
  carrier_id       uuid unique not null references public.active_carriers(id),
  composite_score  numeric(5,2) not null default 100,
  safety_light     text not null default 'green',
  insurance_score  numeric(5,2),
  csa_score        numeric(5,2),
  cdl_score        numeric(5,2),
  ifta_score       numeric(5,2),
  ucr_score        numeric(5,2),
  inspection_score numeric(5,2),
  eld_score        numeric(5,2),
  last_computed_at timestamptz not null default now()
);
create index if not exists idx_comp_scores_light on public.carrier_compliance_scores(safety_light);

-- ── drug_test_schedule ──────────────────────────────────────
create table if not exists public.drug_test_schedule (
  id           uuid primary key default gen_random_uuid(),
  carrier_id   uuid not null references public.active_carriers(id),
  driver_id    text not null,
  driver_name  text,
  test_type    text not null default 'random',
  scheduled_at date not null,
  completed_at date,
  result       text,
  notes        text,
  created_at   timestamptz not null default now()
);
create index if not exists idx_drug_test_carrier   on public.drug_test_schedule(carrier_id);
create index if not exists idx_drug_test_scheduled on public.drug_test_schedule(scheduled_at);

-- ── vehicle_inspections ─────────────────────────────────────
create table if not exists public.vehicle_inspections (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid not null references public.active_carriers(id),
  truck_id        text not null,
  vin             text,
  last_inspection date,
  due_date        date not null,
  result          text not null default 'not_performed',
  defects         text[],
  sticker_expiry  date,
  notes           text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (carrier_id, truck_id)
);
create index if not exists idx_inspections_carrier on public.vehicle_inspections(carrier_id);
create index if not exists idx_inspections_due     on public.vehicle_inspections(due_date);

-- ── ifta_filings ────────────────────────────────────────────
create table if not exists public.ifta_filings (
  id         uuid primary key default gen_random_uuid(),
  carrier_id uuid not null references public.active_carriers(id),
  quarter    text not null,
  due_date   date not null,
  filed_date date,
  status     text not null default 'pending',
  created_at timestamptz not null default now(),
  unique (carrier_id, quarter)
);
create index if not exists idx_ifta_carrier on public.ifta_filings(carrier_id);
create index if not exists idx_ifta_status  on public.ifta_filings(status);

-- ── ucr_registrations ───────────────────────────────────────
create table if not exists public.ucr_registrations (
  id          uuid primary key default gen_random_uuid(),
  carrier_id  uuid not null references public.active_carriers(id),
  reg_year    int not null,
  status      text not null default 'pending',
  expiry_date date,
  fee_paid    numeric(8,2),
  created_at  timestamptz not null default now(),
  unique (carrier_id, reg_year)
);
create index if not exists idx_ucr_carrier on public.ucr_registrations(carrier_id);

-- ── mvr_checks ──────────────────────────────────────────────
create table if not exists public.mvr_checks (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid not null references public.active_carriers(id),
  driver_id       text not null,
  driver_name     text,
  checked_at      date not null,
  next_due        date not null,
  result          text,
  violation_count int not null default 0,
  notes           text,
  created_at      timestamptz not null default now()
);
create index if not exists idx_mvr_carrier  on public.mvr_checks(carrier_id);
create index if not exists idx_mvr_next_due on public.mvr_checks(next_due);

-- ── lease_agreements ────────────────────────────────────────
create table if not exists public.lease_agreements (
  id           uuid primary key default gen_random_uuid(),
  carrier_id   uuid not null references public.active_carriers(id),
  driver_id    text not null,
  driver_name  text,
  lease_type   text not null default 'owner_operator',
  start_date   date not null,
  end_date     date,
  auto_renew   boolean not null default true,
  status       text not null default 'active',
  document_url text,
  created_at   timestamptz not null default now(),
  unique (carrier_id, driver_id)
);
create index if not exists idx_lease_carrier on public.lease_agreements(carrier_id);
create index if not exists idx_lease_status  on public.lease_agreements(status);

-- ── analytics_daily_kpis ────────────────────────────────────
create table if not exists public.analytics_daily_kpis (
  id                uuid primary key default gen_random_uuid(),
  kpi_date          date not null unique,
  gross_revenue     numeric(14,2) not null default 0,
  total_loads       int not null default 0,
  avg_rate_per_mile numeric(6,4),
  avg_margin_pct    numeric(5,2),
  total_miles       int not null default 0,
  fleet_utilization numeric(5,2),
  active_trucks     int not null default 0,
  total_trucks      int not null default 0,
  computed_at       timestamptz not null default now()
);
create index if not exists idx_kpis_date on public.analytics_daily_kpis(kpi_date desc);

-- ── analytics_lane_stats ────────────────────────────────────
create table if not exists public.analytics_lane_stats (
  id                uuid primary key default gen_random_uuid(),
  origin_state      text not null,
  destination_state text not null,
  total_loads       int not null default 0,
  avg_rate_per_mile numeric(6,4),
  avg_margin_pct    numeric(5,2),
  total_revenue     numeric(12,2) not null default 0,
  last_updated_at   timestamptz not null default now(),
  unique (origin_state, destination_state)
);
create index if not exists idx_lane_revenue on public.analytics_lane_stats(total_revenue desc);

-- ── analytics_driver_rankings ───────────────────────────────
create table if not exists public.analytics_driver_rankings (
  id                uuid primary key default gen_random_uuid(),
  carrier_id        uuid references public.active_carriers(id),
  driver_id         text not null,
  driver_name       text,
  total_loads       int not null default 0,
  on_time_pct       numeric(5,2),
  total_miles       int not null default 0,
  performance_score numeric(5,2) not null default 0,
  rank_position     int,
  last_updated_at   timestamptz not null default now(),
  unique (carrier_id, driver_id)
);
create index if not exists idx_driver_rank_score on public.analytics_driver_rankings(performance_score desc);

-- ── analytics_rate_index ────────────────────────────────────
create table if not exists public.analytics_rate_index (
  id                uuid primary key default gen_random_uuid(),
  origin_state      text not null,
  destination_state text not null,
  equipment_type    text not null default 'dry_van',
  sample_count      int not null default 0,
  avg_rate_per_mile numeric(6,4),
  min_rate_per_mile numeric(6,4),
  max_rate_per_mile numeric(6,4),
  p25_rate_per_mile numeric(6,4),
  p75_rate_per_mile numeric(6,4),
  computed_at       timestamptz not null default now(),
  unique (origin_state, destination_state, equipment_type)
);
create index if not exists idx_rate_index_lane on public.analytics_rate_index(origin_state, destination_state);

-- ── analytics_weekly_reports ────────────────────────────────
create table if not exists public.analytics_weekly_reports (
  id                uuid primary key default gen_random_uuid(),
  week_start        date not null unique,
  week_end          date not null,
  gross_revenue     numeric(14,2) not null default 0,
  total_loads       int not null default 0,
  avg_rate_per_mile numeric(6,4),
  fleet_utilization numeric(5,2),
  top_lane          text,
  top_driver        text,
  compliance_score  numeric(5,2),
  dispute_count     int not null default 0,
  report_payload    jsonb not null default '{}',
  generated_at      timestamptz not null default now()
);
create index if not exists idx_weekly_reports_week on public.analytics_weekly_reports(week_start desc);

-- ── analytics_forecasts ─────────────────────────────────────
create table if not exists public.analytics_forecasts (
  id                uuid primary key default gen_random_uuid(),
  forecast_date     date not null,
  horizon_days      int not null,
  projected_revenue numeric(14,2) not null default 0,
  projected_loads   int not null default 0,
  confidence_pct    numeric(5,2),
  methodology       text,
  computed_at       timestamptz not null default now()
);
create index if not exists idx_forecasts_date on public.analytics_forecasts(forecast_date desc);

-- ── carriers (ops hub roster) ───────────────────────────────
create table if not exists public.carriers (
  id                 uuid primary key default gen_random_uuid(),
  full_name          text not null,
  first_name         text,
  last_name          text,
  mc_number          text,
  dot_number         text,
  home_base          text,
  equipment          text default 'Dry Van',
  plan               text default '5% Standard',
  phone              text,
  email              text,
  insurance_provider text,
  eld                text,
  status             text not null default 'New — Pending Onboarding',
  enrolled_date      date default current_date,
  loads_completed    int default 0,
  created_at         timestamptz not null default now()
);
create index if not exists idx_carriers_status  on public.carriers(status);
create index if not exists idx_carriers_created on public.carriers(created_at desc);

-- ── dispatcher_notes ────────────────────────────────────────
create table if not exists public.dispatcher_notes (
  id         uuid primary key default gen_random_uuid(),
  title      text not null,
  body       text,
  category   text default 'General',
  created_at timestamptz not null default now()
);

-- ── RLS for ops hub tables ───────────────────────────────────
alter table public.carriers         enable row level security;
alter table public.dispatcher_notes enable row level security;

drop policy if exists carriers_all         on public.carriers;
drop policy if exists dispatcher_notes_all on public.dispatcher_notes;

create policy carriers_all         on public.carriers         for all using (true) with check (true);
create policy dispatcher_notes_all on public.dispatcher_notes for all using (true) with check (true);

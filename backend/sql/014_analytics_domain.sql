-- Analytics & Intelligence domain tables for execution engine steps 181-200

-- Daily KPI snapshot (upserted by step 181)
create table if not exists analytics_daily_kpis (
  id                uuid primary key default gen_random_uuid(),
  kpi_date          date not null unique,
  gross_revenue     numeric(14,2) not null default 0,
  total_loads       int not null default 0,
  avg_rate_per_mile numeric(6,4),
  avg_margin_pct    numeric(5,2),
  total_miles       int not null default 0,
  fleet_utilization numeric(5,2),   -- pct of trucks active
  active_trucks     int not null default 0,
  total_trucks      int not null default 0,
  computed_at       timestamptz not null default now()
);

create index if not exists idx_analytics_kpis_date on analytics_daily_kpis(kpi_date desc);

-- Lane profitability by origin/dest state pair (upserted by step 183)
create table if not exists analytics_lane_stats (
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

create index if not exists idx_lane_stats_revenue on analytics_lane_stats(total_revenue desc);

-- Driver performance ranking (upserted by step 185)
create table if not exists analytics_driver_rankings (
  id                uuid primary key default gen_random_uuid(),
  carrier_id        uuid references active_carriers(id),
  driver_id         text not null,
  driver_name       text,
  total_loads       int not null default 0,
  on_time_pct       numeric(5,2),
  total_miles       int not null default 0,
  performance_score numeric(5,2) not null default 0,  -- 0-100
  rank_position     int,
  last_updated_at   timestamptz not null default now(),
  unique (carrier_id, driver_id)
);

create index if not exists idx_driver_rankings_score on analytics_driver_rankings(performance_score desc);

-- Internal rate index from executed rate confs (upserted by step 194)
create table if not exists analytics_rate_index (
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

create index if not exists idx_rate_index_lane on analytics_rate_index(origin_state, destination_state);

-- Weekly executive report snapshots (upserted by step 197)
create table if not exists analytics_weekly_reports (
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

create index if not exists idx_weekly_reports_week on analytics_weekly_reports(week_start desc);

-- Revenue forecast snapshots (written by step 186)
create table if not exists analytics_forecasts (
  id               uuid primary key default gen_random_uuid(),
  forecast_date    date not null,
  horizon_days     int not null,   -- 30 | 60 | 90
  projected_revenue numeric(14,2) not null default 0,
  projected_loads  int not null default 0,
  confidence_pct   numeric(5,2),
  methodology      text,
  computed_at      timestamptz not null default now()
);

create index if not exists idx_forecasts_date on analytics_forecasts(forecast_date desc);

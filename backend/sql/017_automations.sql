-- Automation health tracking — monitors all background jobs and integrations
-- Tracks status, last run time, and errors for each automation service

create table if not exists public.automation_health (
  id              uuid primary key default gen_random_uuid(),
  service_name    text not null unique,
  display_name    text not null,

  -- Status
  status          text not null default 'ok',
    -- ok | warning | failed
  last_check_at   timestamptz,
  last_success_at timestamptz,

  -- Error tracking
  error_message   text,
  error_count     int default 0,
  consecutive_failures int default 0,

  -- Metadata
  affected_carriers int,  -- null if not carrier-specific
  run_interval_seconds int,  -- how often it runs
  last_run_duration_ms int,

  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists idx_automation_status on public.automation_health(status);
create index if not exists idx_automation_service on public.automation_health(service_name);
create index if not exists idx_automation_last_check on public.automation_health(last_check_at desc);

-- Insert initial automation records
insert into public.automation_health (service_name, display_name, run_interval_seconds, status) values
  ('eld_sync_motive',       'ELD Sync — Motive',            300, 'ok'),
  ('eld_sync_samsara',      'ELD Sync — Samsara',           300, 'ok'),
  ('eld_sync_geotab',       'ELD Sync — Geotab',            300, 'ok'),
  ('gps_tracking',          'GPS Tracking',                  30, 'ok'),
  ('hos_compliance_check',  'HOS Compliance Check',        3600, 'ok'),
  ('fmcsa_safety_monitor',  'FMCSA Safety Monitor',       21600, 'ok'),
  ('email_ingest_sendgrid', 'Email Ingest (SendGrid)',       0, 'ok'),
  ('email_ingest_imap',     'Email Ingest (IMAP)',         300, 'ok'),
  ('invoice_autosend',      'Invoice Auto-send',          3600, 'ok'),
  ('compliance_sweep',      'Compliance Sweep',           86400, 'ok'),
  ('payout_processing',     'Payout Processing',          3600, 'ok'),
  ('clm_contract_scanner',  'CLM Contract Scanner',          0, 'ok'),
  ('analytics_snapshot',    'Analytics Snapshot',        3600, 'ok'),
  ('carrier_scoring',       'Carrier Performance Scoring', 3600, 'ok')
on conflict (service_name) do nothing;

-- Table: automation_run_log (for detailed history)
create table if not exists public.automation_run_log (
  id              uuid primary key default gen_random_uuid(),
  service_name    text not null references public.automation_health(service_name),
  status          text not null,  -- success | warning | failed
  duration_ms     int,
  items_processed int,
  error_message   text,
  run_at          timestamptz not null default now()
);

create index if not exists idx_automation_log_service on public.automation_run_log(service_name);
create index if not exists idx_automation_log_run_at on public.automation_run_log(run_at desc);

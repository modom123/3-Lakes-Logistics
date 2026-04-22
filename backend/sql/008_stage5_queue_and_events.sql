-- Stage 5 migration (step 61): Task queue, support threads, load matches,
-- Stripe event ledger, scheduled jobs, webhook log, and data-retention marks.
-- Builds on 001-007. All tables live in public.

-- -------- Agent task queue (Vance orchestration) --------
create table if not exists public.agent_tasks (
  id          uuid primary key default gen_random_uuid(),
  agent       text not null,
  kind        text not null,
  payload     jsonb not null default '{}'::jsonb,
  priority    int  not null default 5,
  carrier_id  uuid references public.active_carriers(id) on delete cascade,
  status      text not null default 'pending',
      -- pending | claimed | running | done | error | dead
  attempts    int  not null default 0,
  max_attempts int not null default 3,
  run_at      timestamptz not null default now(),
  claimed_at  timestamptz,
  finished_at timestamptz,
  error       text,
  result      jsonb,
  created_at  timestamptz not null default now()
);
create index if not exists agent_tasks_pending_idx
  on public.agent_tasks (run_at) where status = 'pending';
create index if not exists agent_tasks_agent_idx
  on public.agent_tasks (agent, status);

create table if not exists public.agent_runs (
  id         uuid primary key default gen_random_uuid(),
  task_id    uuid references public.agent_tasks(id) on delete cascade,
  agent      text not null,
  kind       text not null,
  status     text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  duration_ms int,
  input      jsonb,
  output     jsonb,
  error      text
);
create index if not exists agent_runs_agent_idx on public.agent_runs (agent, started_at desc);

-- -------- Load matches (Sonny) --------
create table if not exists public.load_matches (
  id            uuid primary key default gen_random_uuid(),
  carrier_id    uuid not null references public.active_carriers(id) on delete cascade,
  truck_id      text not null,
  driver_id     uuid,
  load_source   text,
  load_ref      text,
  origin        text,
  destination   text,
  miles         int,
  rate_total    numeric(10,2),
  rate_per_mile numeric(6,2),
  trailer_type  text,
  weight_lbs    int,
  score         numeric(5,2),
  status        text not null default 'proposed',
      -- proposed | booked | declined | expired
  created_at    timestamptz not null default now()
);
create index if not exists load_matches_carrier_idx on public.load_matches (carrier_id, status);

-- -------- Support threads (Nova / Signal / Echo) --------
create table if not exists public.support_threads (
  id         uuid primary key default gen_random_uuid(),
  carrier_id uuid references public.active_carriers(id) on delete cascade,
  driver_id  uuid,
  channel    text not null,     -- email | sms | voice | chat
  subject    text,
  status     text not null default 'open',  -- open | waiting | closed
  assigned_agent text,
  last_message_at timestamptz,
  created_at timestamptz not null default now()
);
create table if not exists public.support_messages (
  id         uuid primary key default gen_random_uuid(),
  thread_id  uuid not null references public.support_threads(id) on delete cascade,
  direction  text not null,     -- in | out
  author     text,              -- email / phone / agent name
  body       text,
  meta       jsonb,
  created_at timestamptz not null default now()
);
create index if not exists support_msgs_thread_idx
  on public.support_messages (thread_id, created_at);

-- -------- Stripe event ledger (Penny) --------
create table if not exists public.stripe_events (
  id          text primary key,
  type        text not null,
  carrier_id  uuid references public.active_carriers(id) on delete set null,
  data        jsonb not null,
  processed   boolean not null default false,
  processed_at timestamptz,
  created_at  timestamptz not null default now()
);

-- -------- Webhook inbound log (signature audit) --------
create table if not exists public.webhook_log (
  id         uuid primary key default gen_random_uuid(),
  source     text not null,     -- stripe | motive | vapi | twilio
  event_id   text,
  verified   boolean not null,
  payload    jsonb,
  created_at timestamptz not null default now()
);
create index if not exists webhook_log_source_idx on public.webhook_log (source, created_at desc);

-- -------- Scheduled jobs heartbeat --------
create table if not exists public.scheduled_jobs (
  name         text primary key,
  cron         text not null,
  last_run_at  timestamptz,
  last_status  text,
  last_error   text,
  enabled      boolean not null default true
);

-- -------- Data retention marks (step 79) --------
create table if not exists public.retention_marks (
  id         uuid primary key default gen_random_uuid(),
  table_name text not null,
  row_id     uuid not null,
  reason     text not null,     -- user_request | policy_ttl
  purged_at  timestamptz,
  created_at timestamptz not null default now()
);

-- -------- Auth role mapping (step 72) --------
alter table public.carrier_user_map
  add column if not exists permissions jsonb default '[]'::jsonb;

-- -------- Driver settlements (Settler, step 66) --------
create table if not exists public.driver_settlements (
  id           uuid primary key default gen_random_uuid(),
  carrier_id   uuid not null references public.active_carriers(id) on delete cascade,
  driver_id    uuid,
  period_start date not null,
  period_end   date not null,
  gross_amount numeric(10,2) not null default 0,
  deductions   numeric(10,2) not null default 0,
  net_amount   numeric(10,2) generated always as (gross_amount - deductions) stored,
  pdf_url      text,
  ach_ref      text,
  status       text not null default 'draft',  -- draft | sent | paid | failed
  created_at   timestamptz not null default now()
);
create index if not exists settlements_carrier_idx
  on public.driver_settlements (carrier_id, period_end desc);

alter table public.agent_tasks        enable row level security;
alter table public.agent_runs         enable row level security;
alter table public.load_matches       enable row level security;
alter table public.support_threads    enable row level security;
alter table public.support_messages   enable row level security;
alter table public.stripe_events      enable row level security;
alter table public.webhook_log        enable row level security;
alter table public.scheduled_jobs     enable row level security;
alter table public.retention_marks    enable row level security;
alter table public.driver_settlements enable row level security;

create policy tasks_admin_only     on public.agent_tasks        for select using (public.is_admin());
create policy runs_admin_only      on public.agent_runs         for select using (public.is_admin());
create policy matches_read_own     on public.load_matches       for select using (carrier_id = public.current_carrier_id() or public.is_admin());
create policy threads_read_own     on public.support_threads    for select using (carrier_id = public.current_carrier_id() or public.is_admin());
create policy msgs_read_own        on public.support_messages   for select using (exists (
  select 1 from public.support_threads t
  where t.id = thread_id and (t.carrier_id = public.current_carrier_id() or public.is_admin())
));
create policy stripe_events_admin  on public.stripe_events      for select using (public.is_admin());
create policy webhooks_admin       on public.webhook_log        for select using (public.is_admin());
create policy jobs_admin           on public.scheduled_jobs     for select using (public.is_admin());
create policy retention_admin      on public.retention_marks    for select using (public.is_admin());
create policy settlements_read_own on public.driver_settlements for select using (carrier_id = public.current_carrier_id() or public.is_admin());

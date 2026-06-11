-- 025 · scheduled_tasks — deferred onboarding / reminder work, polled hourly by
-- triggers.fire_scheduled_tasks() and the onboarding scheduler. Referenced by
-- backend/app/execution_engine/handlers/* and the James Bond onboarding audit,
-- but never previously declared in a migration. Idempotent.

create table if not exists public.scheduled_tasks (
  id            uuid primary key default gen_random_uuid(),
  task_type     text not null,
  carrier_id    text,
  payload       jsonb not null default '{}'::jsonb,
  scheduled_for timestamptz,
  status        text not null default 'pending',  -- pending | completed | failed
  attempts      int  not null default 0,
  executed_at   timestamptz,
  result        jsonb,
  error         text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index if not exists idx_sched_tasks_due     on public.scheduled_tasks (status, scheduled_for);
create index if not exists idx_sched_tasks_carrier on public.scheduled_tasks (carrier_id, task_type);

alter table public.scheduled_tasks enable row level security;
drop policy if exists sched_tasks_service on public.scheduled_tasks;
create policy sched_tasks_service on public.scheduled_tasks using (true) with check (true);

-- 024 · executive_escalations — Tier-N escalations raised by Outside Bond and
-- the IEBC technical team, assigned to executives (Mark Odom, CC Gulley, ...).
-- Referenced by backend/app/agents/outside_bond.py (_create_escalation) and the
-- security test-suite, but never previously declared in a migration. Idempotent.

create table if not exists public.executive_escalations (
  id           uuid primary key default gen_random_uuid(),
  tier         int  not null default 2,
  event_type   text not null,
  description  text not null,
  assigned_to  text,
  status       text not null default 'open',     -- open | acknowledged | resolved
  resolution   text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists idx_exec_esc_status   on public.executive_escalations (status, created_at);
create index if not exists idx_exec_esc_assigned on public.executive_escalations (assigned_to, status);

alter table public.executive_escalations enable row level security;
drop policy if exists exec_esc_service on public.executive_escalations;
create policy exec_esc_service on public.executive_escalations using (true) with check (true);

-- 022 · Office shared state (key/value)
-- Backs the executive offices' shared TODO list and "My Contacts" so they
-- persist server-side and sync across users/devices instead of living only in
-- each browser's localStorage. Generic jsonb KV — one row per key
-- (e.g. 'mo_todos', 'oc_mark', 'oc_cece'). Idempotent.

create table if not exists public.office_state (
  key        text primary key,
  value      jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.office_state enable row level security;
drop policy if exists office_state_service on public.office_state;
create policy office_state_service on public.office_state using (true) with check (true);

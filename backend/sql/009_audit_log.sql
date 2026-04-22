-- Stage 5 step 75: immutable audit log for mutations + security events.
create table if not exists public.audit_log (
  id          uuid primary key default gen_random_uuid(),
  actor       text not null,           -- service | user:<uid> | agent:<name>
  action      text not null,           -- create|update|delete|login|plan_change|...
  entity      text,                    -- table or domain object
  entity_id   text,
  carrier_id  uuid,
  meta        jsonb,
  ip          inet,
  user_agent  text,
  ts          timestamptz not null default now()
);

create index if not exists audit_log_entity_idx on public.audit_log (entity, entity_id);
create index if not exists audit_log_actor_idx  on public.audit_log (actor, ts desc);
create index if not exists audit_log_carrier_idx on public.audit_log (carrier_id, ts desc);

-- Make it append-only: block UPDATE + DELETE to anyone (including service role).
revoke update, delete on public.audit_log from public;

create or replace function public._audit_log_immutable()
returns trigger language plpgsql as $$
begin
  raise exception 'audit_log is append-only';
end; $$;

drop trigger if exists audit_log_no_mutate on public.audit_log;
create trigger audit_log_no_mutate
  before update or delete on public.audit_log
  for each row execute function public._audit_log_immutable();

alter table public.audit_log enable row level security;
create policy audit_admin on public.audit_log for select using (public.is_admin());

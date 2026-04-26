-- Execution Engine: tracks every run of the 200-step autonomous workflow
create table if not exists execution_steps (
  id              uuid primary key default gen_random_uuid(),
  step_number     int not null,
  step_name       text not null,
  domain          text not null,
  -- pending | running | complete | failed | skipped
  status          text not null default 'pending',
  carrier_id      uuid references active_carriers(id),
  contract_id     uuid references contracts(id),
  input_payload   jsonb not null default '{}',
  output_payload  jsonb not null default '{}',
  error_message   text,
  started_at      timestamptz,
  completed_at    timestamptz,
  duration_ms     int,
  created_at      timestamptz not null default now()
);

create index if not exists idx_execution_steps_number   on execution_steps(step_number);
create index if not exists idx_execution_steps_domain   on execution_steps(domain);
create index if not exists idx_execution_steps_status   on execution_steps(status);
create index if not exists idx_execution_steps_carrier  on execution_steps(carrier_id);

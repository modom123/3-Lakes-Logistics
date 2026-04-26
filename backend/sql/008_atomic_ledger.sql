-- Atomic Ledger: immutable unified event store linking every dispatch,
-- contract, and accounting action into a single auditable timeline.
create table if not exists atomic_ledger (
  id                  uuid primary key default gen_random_uuid(),
  event_type          text not null,
  event_source        text not null,
  tenant_id           uuid,
  logistics_payload   jsonb not null default '{}',
  financial_payload   jsonb not null default '{}',
  compliance_payload  jsonb not null default '{}',
  metadata            jsonb not null default '{}',
  created_at          timestamptz not null default now()
);

create index if not exists idx_atomic_ledger_event_type  on atomic_ledger(event_type);
create index if not exists idx_atomic_ledger_created_at  on atomic_ledger(created_at desc);
create index if not exists idx_atomic_ledger_tenant      on atomic_ledger(tenant_id);
create index if not exists idx_atomic_ledger_logistics   on atomic_ledger using gin(logistics_payload);
create index if not exists idx_atomic_ledger_financial   on atomic_ledger using gin(financial_payload);

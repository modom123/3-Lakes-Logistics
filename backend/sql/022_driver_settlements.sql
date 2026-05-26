-- ============================================================
-- Migration 022: Driver Settlements — weekly pay statements
-- Stores generated weekly settlement records so dispatchers and
-- drivers have a permanent, auditable pay history.
-- ============================================================

create table if not exists public.driver_settlements (
  id              uuid primary key default gen_random_uuid(),
  driver_id       uuid references public.drivers(id) on delete set null,
  carrier_id      uuid references public.active_carriers(id) on delete set null,
  driver_name     text,                          -- denormalized for display
  week_start      date not null,                 -- Monday of the pay week
  week_end        date not null,                 -- Sunday of the pay week
  load_count      int not null default 0,
  total_miles     int not null default 0,
  gross_pay       numeric(10,2) not null default 0,
  dispatch_fee    numeric(10,2) not null default 0,
  fuel_advance    numeric(10,2) not null default 0,
  insurance_deduction numeric(10,2) not null default 0,
  other_deductions numeric(10,2) not null default 0,
  net_pay         numeric(10,2) not null default 0,
  status          text not null default 'draft',  -- draft | sent | acknowledged
  sent_at         timestamptz,
  sent_to         text,
  load_ids        uuid[],                         -- all loads included
  notes           text,
  created_at      timestamptz not null default now()
);

create index if not exists idx_driver_settlements_driver  on public.driver_settlements(driver_id);
create index if not exists idx_driver_settlements_week    on public.driver_settlements(week_start desc);
create index if not exists idx_driver_settlements_carrier on public.driver_settlements(carrier_id);

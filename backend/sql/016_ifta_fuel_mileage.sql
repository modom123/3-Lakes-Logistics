-- IFTA mileage by state per quarter
create table if not exists ifta_mileage (
  id          uuid primary key default gen_random_uuid(),
  carrier_id  uuid not null references active_carriers(id) on delete cascade,
  quarter     text not null,
  state_code  text not null,
  miles       numeric(10,1) not null default 0,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (carrier_id, quarter, state_code)
);

create index if not exists idx_ifta_mileage_carrier  on ifta_mileage(carrier_id);
create index if not exists idx_ifta_mileage_quarter  on ifta_mileage(quarter);

-- IFTA fuel purchases per state per quarter
create table if not exists ifta_fuel (
  id            uuid primary key default gen_random_uuid(),
  carrier_id    uuid not null references active_carriers(id) on delete cascade,
  quarter       text not null,
  state_code    text not null,
  gallons       numeric(10,3) not null default 0,
  amount_usd    numeric(10,2),
  purchase_date date,
  notes         text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index if not exists idx_ifta_fuel_carrier  on ifta_fuel(carrier_id);
create index if not exists idx_ifta_fuel_quarter  on ifta_fuel(quarter);

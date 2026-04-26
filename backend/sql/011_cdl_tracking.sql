-- CDL (Commercial Driver's License) tracking for all drivers
-- Enables Shield agent to monitor expiry and auto-alert/suspend

create table if not exists driver_cdl (
  id               uuid primary key default gen_random_uuid(),
  carrier_id       uuid not null references active_carriers(id) on delete cascade,
  driver_id        text not null,
  driver_name      text,
  cdl_number       text,
  cdl_state        text,
  cdl_class        text,          -- A | B | C
  -- Endorsements: H=Hazmat, T=Tank, N=Tank, X=HazTank, P=Passenger, S=School
  endorsements     text[],
  -- Restrictions: L=No Air Brakes, Z=No Full Air, K=Intrastate Only
  restrictions     text[],
  cdl_expiry       date not null,
  medical_card_expiry date,       -- DOT physical card (2-year cycle)
  clearinghouse_enrolled boolean default false,
  mvr_last_checked date,
  -- green | yellow | red
  cdl_status       text not null default 'green',
  notes            text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (carrier_id, driver_id)
);

create index if not exists idx_driver_cdl_carrier  on driver_cdl(carrier_id);
create index if not exists idx_driver_cdl_expiry   on driver_cdl(cdl_expiry);
create index if not exists idx_driver_cdl_status   on driver_cdl(cdl_status);
create index if not exists idx_driver_cdl_medical  on driver_cdl(medical_card_expiry);

-- Add CDL fields to driver_hos_status if columns not present
alter table driver_hos_status
  add column if not exists cdl_number text,
  add column if not exists cdl_expiry date,
  add column if not exists cdl_status text default 'green';

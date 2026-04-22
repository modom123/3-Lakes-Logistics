-- Step 8: driver_hos_status — Hours-of-Service from ELD. Refreshed on
-- every Motive/Samsara webhook event and on dispatch lookups.

create table if not exists public.drivers (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid not null references public.active_carriers(id) on delete cascade,
  driver_code     text not null,
  first_name      text,
  last_name       text,
  cdl_number      text,
  cdl_state       text(2),
  cdl_expires     date,
  medical_card_expires date,
  phone           text,
  email           text,
  hire_date       date,
  status          text default 'active',
  created_at      timestamptz not null default now(),
  unique (carrier_id, driver_code)
);

create table if not exists public.driver_hos_status (
  id              bigserial primary key,
  carrier_id      uuid not null references public.active_carriers(id) on delete cascade,
  driver_id       uuid references public.drivers(id) on delete cascade,
  driver_code     text,
  duty_status     text,          -- on_duty | driving | sleeper | off_duty
  drive_remaining_min int,
  shift_remaining_min int,
  cycle_remaining_min int,
  violation_flags text[],        -- e.g. {'approaching_11hr','hos_violation'}
  ts              timestamptz not null default now()
);

create index if not exists idx_hos_carrier on public.driver_hos_status(carrier_id, ts desc);
create index if not exists idx_hos_driver on public.driver_hos_status(driver_id, ts desc);

-- Step 5: fleet_assets — one row per truck/trailer. Populated from
-- intake Step 2 and kept in sync with ELD via Motive/Samsara/Geotab.

create table if not exists public.fleet_assets (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid not null references public.active_carriers(id) on delete cascade,
  truck_id        text not null,
  vin             text,
  year            int,
  make            text,
  model           text,
  trailer_type    text,
    -- dry_van | reefer | flatbed | step_deck | box26 | cargo_van | tanker_hazmat | hotshot | auto
  max_weight_lbs  int,
  equipment_count int default 1,

  status          text not null default 'available',
    -- available | on_load | out_of_service | maintenance
  current_location jsonb,
  last_hos_update timestamptz,

  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (carrier_id, truck_id)
);

create index if not exists idx_fleet_carrier on public.fleet_assets(carrier_id);
create index if not exists idx_fleet_status on public.fleet_assets(status);
create index if not exists idx_fleet_trailer on public.fleet_assets(trailer_type);

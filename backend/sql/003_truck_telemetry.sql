-- Step 6: truck_telemetry — live GPS pings from ELD providers.
-- Scale target: 1,000 trucks * ~1 ping/min = ~1.4M rows/day.

create table if not exists public.truck_telemetry (
  id              bigserial primary key,
  carrier_id      uuid not null references public.active_carriers(id) on delete cascade,
  truck_id        text not null,
  eld_provider    text,  -- motive | samsara | geotab | omnitracs
  lat             double precision,
  lng             double precision,
  speed_mph       double precision,
  heading_deg     double precision,
  odometer_mi     double precision,
  fuel_level_pct  double precision,
  engine_hours    double precision,
  ts              timestamptz not null default now()
);

create index if not exists idx_telemetry_truck_ts on public.truck_telemetry(carrier_id, truck_id, ts desc);
create index if not exists idx_telemetry_ts on public.truck_telemetry(ts desc);

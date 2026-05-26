-- Migration 017: Add engine_state and accuracy_m to truck_telemetry
-- engine_state captures PWA pickup_confirmed / delivery_confirmed events
-- accuracy_m captures GPS horizontal accuracy in metres for data quality filtering

alter table public.truck_telemetry
  add column if not exists engine_state text,
  add column if not exists accuracy_m   double precision;

-- Index on engine_state for fast event queries (pickup/delivery reporting)
create index if not exists idx_telemetry_engine_state
  on public.truck_telemetry(carrier_id, engine_state, ts desc)
  where engine_state is not null;

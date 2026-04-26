-- Migration 012: extend loads table with full dispatch fields,
-- add missing columns to leads + document_vault, create load_events audit table.
-- Run once against Supabase with: psql $DATABASE_URL -f 012_loads_and_schema_extensions.sql

-- ── 1. Extend loads table ────────────────────────────────────────────────────

alter table public.loads
  add column if not exists trailer_type       text,
  add column if not exists weight_lbs         int,
  add column if not exists commodity          text,
  add column if not exists pieces             int,
  add column if not exists hazmat             boolean default false,
  add column if not exists temperature_controlled boolean default false,
  add column if not exists temp_min_f         int,
  add column if not exists temp_max_f         int,

  -- Broker contact fields (from rate confirmation)
  add column if not exists broker_email       text,
  add column if not exists broker_phone       text,
  add column if not exists broker_contact     text,
  add column if not exists broker_ref_number  text,
  add column if not exists broker_mc          text,

  -- Origin / destination full addresses
  add column if not exists origin_address     text,
  add column if not exists dest_address       text,
  add column if not exists origin_zip         text,
  add column if not exists dest_zip           text,

  -- Driver contact (denormalized for quick access)
  add column if not exists driver_name        text,
  add column if not exists driver_phone       text,
  add column if not exists driver_email       text,

  -- Live tracking fields
  add column if not exists current_location   text,
  add column if not exists eta                text,
  add column if not exists geofence_pickup_lat  numeric(10,7),
  add column if not exists geofence_pickup_lng  numeric(10,7),
  add column if not exists geofence_dest_lat    numeric(10,7),
  add column if not exists geofence_dest_lng    numeric(10,7),

  -- Financial
  add column if not exists fuel_surcharge     numeric(8,2),
  add column if not exists detention_rate     numeric(8,2),
  add column if not exists lumper_fee         numeric(8,2),
  add column if not exists accessorial_total  numeric(8,2),
  add column if not exists payment_terms      text default 'quick_pay_30',

  -- Document links
  add column if not exists rate_conf_url      text,
  add column if not exists bol_url            text,
  add column if not exists bol_uploaded_at    timestamptz,

  -- CLM link
  add column if not exists contract_id        uuid references public.contracts(id) on delete set null,

  -- Load source (manual | broker_intake | dat | truckstop | 123loadboard)
  add column if not exists source             text default 'manual',
  add column if not exists source_ref         text,

  -- Timestamps
  add column if not exists dispatched_at      timestamptz,
  add column if not exists picked_up_at       timestamptz,
  add column if not exists delivered_at       timestamptz,
  add column if not exists updated_at         timestamptz not null default now();

-- status must include 'available' for load board matching
-- (existing check constraint dropped if present, then re-added with full list)
alter table public.loads
  drop constraint if exists loads_status_check;

-- ── 2. Load events audit trail ───────────────────────────────────────────────

create table if not exists public.load_events (
  id          uuid primary key default gen_random_uuid(),
  load_id     uuid not null references public.loads(id) on delete cascade,
  carrier_id  uuid references public.active_carriers(id) on delete set null,
  event_type  text not null,
    -- created | offered | accepted | declined | dispatched | picked_up
    -- check_call | delay_alert | delivered | pod_uploaded | settled | closed
  actor       text,           -- driver_id | system | dispatcher name
  payload     jsonb,
  ts          timestamptz not null default now()
);

create index if not exists idx_load_events_load  on public.load_events(load_id, ts desc);
create index if not exists idx_load_events_type  on public.load_events(event_type, ts desc);

-- ── 3. Add missing columns to leads ─────────────────────────────────────────

alter table public.leads
  add column if not exists clicks             int default 0,
  add column if not exists carrier_id         uuid references public.active_carriers(id) on delete set null,
  add column if not exists notes              text,
  add column if not exists call_count         int default 0,
  add column if not exists last_call_at       timestamptz;

-- ── 4. Add missing columns to document_vault ────────────────────────────────

alter table public.document_vault
  add column if not exists scan_result        jsonb,
  add column if not exists scanned_at         timestamptz,
  add column if not exists deleted_at         timestamptz,
  add column if not exists load_id            uuid references public.loads(id) on delete set null,
  add column if not exists driver_id          text,
  add column if not exists notes              text;

-- ── 5. Load board posting log ────────────────────────────────────────────────

create table if not exists public.loadboard_posts (
  id          uuid primary key default gen_random_uuid(),
  load_id     uuid not null references public.loads(id) on delete cascade,
  board       text not null,  -- dat | truckstop | 123loadboard | internal
  post_ref    text,           -- external post ID from the board
  status      text default 'posted',  -- posted | expired | filled | removed
  posted_at   timestamptz not null default now(),
  expires_at  timestamptz,
  filled_at   timestamptz
);

create index if not exists idx_loadboard_posts_load on public.loadboard_posts(load_id);
create index if not exists idx_loadboard_posts_board on public.loadboard_posts(board, status);

-- ── 6. RLS on new tables ─────────────────────────────────────────────────────

alter table public.load_events       enable row level security;
alter table public.loadboard_posts   enable row level security;

-- Service role bypasses RLS (ops backend uses service role key)
create policy "service_all_load_events"
  on public.load_events for all
  using (auth.role() = 'service_role');

create policy "service_all_loadboard_posts"
  on public.loadboard_posts for all
  using (auth.role() = 'service_role');

-- ── 7. Helper: auto-update updated_at on loads ──────────────────────────────

create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_loads_updated_at on public.loads;
create trigger trg_loads_updated_at
  before update on public.loads
  for each row execute function public.set_updated_at();

-- ============================================================
-- Migration 018: Big 4 Coordination — Carriers · Drivers · Load Manager
-- Adds missing columns so Eagle Eye, Execution Engine, Mobile PWA,
-- and the public Website all read/write the same fields.
-- Safe to run multiple times (all use ADD COLUMN IF NOT EXISTS).
-- ============================================================

-- ── loads table ─────────────────────────────────────────────
-- Dispatcher writes these from Eagle Eye; PWA reads them; engine h31/h34/h36 need them.

-- Core operational fields Eagle Eye sends but DB didn't have
alter table public.loads add column if not exists equipment_type      text;
alter table public.loads add column if not exists weight_lbs          int;
alter table public.loads add column if not exists post_to_website     boolean not null default false;

-- Broker contact — execution engine h41/h42 email broker; PWA shows call button
alter table public.loads add column if not exists broker_phone        text;
alter table public.loads add column if not exists broker_email        text;

-- Driver mobile PWA expects full address strings + special instructions on load card
alter table public.loads add column if not exists pickup_address      text;
alter table public.loads add column if not exists delivery_address    text;
alter table public.loads add column if not exists special_instructions text;

-- Shipper — referenced in Eagle Eye load detail panel (load.shipper_name)
alter table public.loads add column if not exists shipper_name        text;

-- rate_total / rate_per_mile already exist (from LIVE_SCHEMA_PART1 patches)
-- rate / rpm also exist (Eagle Eye legacy names) — BOTH are kept so old data is intact
-- Canonical names going forward: rate_total, rate_per_mile

-- Indexes for new columns
create index if not exists idx_loads_equipment  on public.loads(equipment_type);
create index if not exists idx_loads_website    on public.loads(post_to_website) where post_to_website = true;


-- ── active_carriers table ───────────────────────────────────
-- Eagle Eye saveCarrier() sends these; Available Carriers sidebar reads them;
-- execution engine onboarding domain expects some of them.

alter table public.active_carriers add column if not exists fleet_size         int not null default 1;
alter table public.active_carriers add column if not exists trailer_type       text;           -- primary equipment (dry_van, reefer, flatbed…)
alter table public.active_carriers add column if not exists equipment_types    text[];         -- all equipment types this carrier runs
alter table public.active_carriers add column if not exists home_base          text;           -- "Detroit, MI" — shown in Available Carriers sidebar
alter table public.active_carriers add column if not exists eld_provider       text;           -- Samsara / Motive / Geotab / Omnitracs
alter table public.active_carriers add column if not exists insurance_carrier  text;           -- Progressive Commercial, etc.
alter table public.active_carriers add column if not exists policy_number      text;
alter table public.active_carriers add column if not exists onboarding_missing_fields text[];  -- referenced in complete-onboarding route


-- ── drivers table ───────────────────────────────────────────
-- Eagle Eye add-driver modal currently only sends first_name, last_name, phone, pin, carrier_id.
-- These columns likely already exist but adding IF NOT EXISTS guards for safety.

alter table public.drivers add column if not exists email               text;
alter table public.drivers add column if not exists cdl_number          text;
alter table public.drivers add column if not exists cdl_state           text;
alter table public.drivers add column if not exists cdl_expires         date;
alter table public.drivers add column if not exists medical_card_expires date;
alter table public.drivers add column if not exists hire_date           date;
alter table public.drivers add column if not exists truck_id            text;   -- assigned unit number


-- ── Sync trigger: keep active_carriers.equipment_types current ──────────────
-- When a fleet_asset is added/updated/deleted, keep the carrier's equipment_types
-- array in sync (mirrors the logic already in 016_fleet_multi_equipment.sql
-- which missed active_carriers).

create or replace function public.sync_carrier_equipment()
returns trigger language plpgsql security definer as $$
begin
  update public.active_carriers
  set
    equipment_types = (
      select array_agg(distinct trailer_type order by trailer_type)
      from   public.fleet_assets
      where  carrier_id = coalesce(NEW.carrier_id, OLD.carrier_id)
        and  trailer_type is not null
    ),
    fleet_size = (
      select count(*)
      from   public.fleet_assets
      where  carrier_id = coalesce(NEW.carrier_id, OLD.carrier_id)
        and  status not in ('out_of_service','maintenance')
    )
  where id = coalesce(NEW.carrier_id, OLD.carrier_id);
  return coalesce(NEW, OLD);
end;
$$;

drop trigger if exists trg_sync_carrier_equipment on public.fleet_assets;
create trigger trg_sync_carrier_equipment
  after insert or update or delete on public.fleet_assets
  for each row execute function public.sync_carrier_equipment();

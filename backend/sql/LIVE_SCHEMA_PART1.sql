-- ============================================================
-- 3 Lakes Logistics — LIVE SCHEMA PART 1 of 3
-- Tables: active_carriers, fleet_assets, truck_telemetry,
--         leads, drivers, driver_hos_status, eld_connections,
--         insurance_compliance, banking_accounts, signatures_audit,
--         founders_inventory, loads, invoices, agent_log, RLS
-- ============================================================

create extension if not exists "pgcrypto";

-- ── active_carriers ─────────────────────────────────────────
create table if not exists public.active_carriers (
  id                     uuid primary key default gen_random_uuid(),
  company_name           text not null,
  legal_entity           text,
  dot_number             text unique,
  mc_number              text unique,
  ein                    text,
  phone                  text,
  email                  text,
  address                text,
  years_in_business      int,
  plan                   text not null default 'founders',
  stripe_customer_id     text,
  stripe_subscription_id text,
  subscription_status    text default 'pending',
  esign_name             text,
  esign_ip               text,
  esign_user_agent       text,
  esign_timestamp        timestamptz,
  agreement_pdf_hash     text,
  status                 text not null default 'onboarding',
  compliance_suspended         boolean not null default false,
  suspension_reason            text,
  suspended_at                 timestamptz,
  onboarding_missing_fields    text[],
  onboarded_at                 timestamptz,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);
create index if not exists idx_ac_dot    on public.active_carriers(dot_number);
create index if not exists idx_ac_mc     on public.active_carriers(mc_number);
create index if not exists idx_ac_status on public.active_carriers(status);

-- patch missing columns if table already existed
alter table public.active_carriers add column if not exists compliance_suspended       boolean not null default false;
alter table public.active_carriers add column if not exists suspension_reason          text;
alter table public.active_carriers add column if not exists suspended_at               timestamptz;
alter table public.active_carriers add column if not exists onboarding_missing_fields  text[];

-- ── fleet_assets ────────────────────────────────────────────
create table if not exists public.fleet_assets (
  id               uuid primary key default gen_random_uuid(),
  carrier_id       uuid not null references public.active_carriers(id) on delete cascade,
  truck_id         text not null,
  vin              text,
  year             int,
  make             text,
  model            text,
  trailer_type     text,
  max_weight_lbs   int,
  equipment_count  int default 1,
  status           text not null default 'available',
  current_location jsonb,
  last_hos_update  timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (carrier_id, truck_id)
);
alter table public.fleet_assets add column if not exists trailer_type     text;
alter table public.fleet_assets add column if not exists max_weight_lbs   int;
alter table public.fleet_assets add column if not exists equipment_count  int default 1;
alter table public.fleet_assets add column if not exists current_location jsonb;
alter table public.fleet_assets add column if not exists last_hos_update  timestamptz;
create index if not exists idx_fleet_carrier  on public.fleet_assets(carrier_id);
create index if not exists idx_fleet_status   on public.fleet_assets(status);
create index if not exists idx_fleet_trailer  on public.fleet_assets(trailer_type);

-- ── truck_telemetry ─────────────────────────────────────────
create table if not exists public.truck_telemetry (
  id             bigserial primary key,
  carrier_id     uuid not null references public.active_carriers(id) on delete cascade,
  truck_id       text not null,
  eld_provider   text,
  lat            double precision,
  lng            double precision,
  speed_mph      double precision,
  heading_deg    double precision,
  odometer_mi    double precision,
  fuel_level_pct double precision,
  engine_hours   double precision,
  ts             timestamptz not null default now()
);
alter table public.truck_telemetry add column if not exists ts timestamptz not null default now();
create index if not exists idx_telemetry_truck_ts on public.truck_telemetry(carrier_id, truck_id, ts desc);
create index if not exists idx_telemetry_ts       on public.truck_telemetry(ts desc);

-- ── leads ───────────────────────────────────────────────────
create table if not exists public.leads (
  id              uuid primary key default gen_random_uuid(),
  source          text not null,
  source_ref      text,
  company_name    text,
  dot_number      text,
  mc_number       text,
  contact_name    text,
  contact_title   text,
  phone           text,
  email           text,
  address         text,
  fleet_size      int,
  equipment_types text[],
  score           int,
  stage           text default 'new',
  owner_agent     text,
  last_touch_at   timestamptz,
  next_touch_at   timestamptz,
  do_not_contact  boolean default false,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
alter table public.leads add column if not exists source_ref      text;
alter table public.leads add column if not exists company_name    text;
alter table public.leads add column if not exists dot_number      text;
alter table public.leads add column if not exists mc_number       text;
alter table public.leads add column if not exists contact_name    text;
alter table public.leads add column if not exists contact_title   text;
alter table public.leads add column if not exists phone           text;
alter table public.leads add column if not exists email           text;
alter table public.leads add column if not exists address         text;
alter table public.leads add column if not exists fleet_size      int;
alter table public.leads add column if not exists equipment_types text[];
alter table public.leads add column if not exists score           int;
alter table public.leads add column if not exists stage           text default 'new';
alter table public.leads add column if not exists owner_agent     text;
alter table public.leads add column if not exists last_touch_at   timestamptz;
alter table public.leads add column if not exists next_touch_at   timestamptz;
alter table public.leads add column if not exists do_not_contact  boolean default false;
alter table public.leads add column if not exists updated_at      timestamptz not null default now();
create unique index if not exists idx_leads_dot        on public.leads(dot_number) where dot_number is not null;
create unique index if not exists idx_leads_mc         on public.leads(mc_number)  where mc_number  is not null;
create index        if not exists idx_leads_stage      on public.leads(stage);
create index        if not exists idx_leads_score      on public.leads(score desc);
create index        if not exists idx_leads_next_touch on public.leads(next_touch_at) where do_not_contact = false;

-- ── drivers ─────────────────────────────────────────────────
create table if not exists public.drivers (
  id                   uuid primary key default gen_random_uuid(),
  carrier_id           uuid not null references public.active_carriers(id) on delete cascade,
  driver_code          text not null,
  first_name           text,
  last_name            text,
  cdl_number           text,
  cdl_state            text,
  cdl_expires          date,
  medical_card_expires date,
  phone                text,
  email                text,
  hire_date            date,
  status               text default 'active',
  created_at           timestamptz not null default now(),
  unique (carrier_id, driver_code)
);

-- ── driver_hos_status ───────────────────────────────────────
create table if not exists public.driver_hos_status (
  id                  bigserial primary key,
  carrier_id          uuid not null references public.active_carriers(id) on delete cascade,
  driver_id           uuid references public.drivers(id) on delete cascade,
  driver_code         text,
  duty_status         text,
  drive_remaining_min int,
  shift_remaining_min int,
  cycle_remaining_min int,
  violation_flags     text[],
  cdl_number          text,
  cdl_expiry          date,
  cdl_status          text default 'green',
  ts                  timestamptz not null default now()
);
alter table public.driver_hos_status add column if not exists driver_id           uuid;
alter table public.driver_hos_status add column if not exists driver_code         text;
alter table public.driver_hos_status add column if not exists duty_status         text;
alter table public.driver_hos_status add column if not exists drive_remaining_min int;
alter table public.driver_hos_status add column if not exists shift_remaining_min int;
alter table public.driver_hos_status add column if not exists cycle_remaining_min int;
alter table public.driver_hos_status add column if not exists violation_flags     text[];
alter table public.driver_hos_status add column if not exists cdl_number          text;
alter table public.driver_hos_status add column if not exists cdl_expiry          date;
alter table public.driver_hos_status add column if not exists cdl_status          text default 'green';
alter table public.driver_hos_status add column if not exists ts                  timestamptz not null default now();
create index if not exists idx_hos_carrier on public.driver_hos_status(carrier_id, ts desc);
create index if not exists idx_hos_driver  on public.driver_hos_status(driver_id,  ts desc);

-- ── eld_connections ─────────────────────────────────────────
create table if not exists public.eld_connections (
  id             uuid primary key default gen_random_uuid(),
  carrier_id     uuid not null references public.active_carriers(id) on delete cascade,
  eld_provider   text not null,
  eld_api_token  text,
  eld_account_id text,
  status         text default 'pending',
  last_sync_at   timestamptz,
  created_at     timestamptz not null default now(),
  unique (carrier_id, eld_provider)
);

-- ── insurance_compliance ────────────────────────────────────
create table if not exists public.insurance_compliance (
  id                    uuid primary key default gen_random_uuid(),
  carrier_id            uuid not null unique references public.active_carriers(id) on delete cascade,
  insurance_carrier     text,
  policy_number         text,
  policy_expiry         date,
  coi_url               text,
  bmc91_ack             boolean default false,
  mcs90_ack             boolean default false,
  safer_consent         boolean default false,
  csa_consent           boolean default false,
  clearinghouse_consent boolean default false,
  psp_consent           boolean default false,
  safety_light          text default 'yellow',
  last_checked_at       timestamptz,
  created_at            timestamptz not null default now()
);

-- ── banking_accounts ────────────────────────────────────────
create table if not exists public.banking_accounts (
  id                 uuid primary key default gen_random_uuid(),
  carrier_id         uuid not null unique references public.active_carriers(id) on delete cascade,
  bank_routing_last4 text,
  bank_account_last4 text,
  account_token      text,
  account_type       text,
  payee_name         text,
  w9_url             text,
  verified_at        timestamptz,
  created_at         timestamptz not null default now()
);

-- ── signatures_audit ────────────────────────────────────────
create table if not exists public.signatures_audit (
  id         uuid primary key default gen_random_uuid(),
  carrier_id uuid references public.active_carriers(id) on delete cascade,
  doc_type   text,
  esign_name text,
  ip         text,
  user_agent text,
  pdf_hash   text,
  signed_at  timestamptz not null default now()
);

-- ── founders_inventory ──────────────────────────────────────
create table if not exists public.founders_inventory (
  category     text primary key,
  display_name text,
  total        int not null,
  claimed      int not null default 0,
  reserved     int not null default 0
);
insert into public.founders_inventory (category, display_name, total, claimed) values
  ('dry_van',   'Dry Van',                 300, 0),
  ('reefer',    'Reefer',                  200, 0),
  ('flatbed',   'Flatbed / Step Deck',     150, 0),
  ('box_truck', 'Box Truck 26ft Non-CDL',  100, 0),
  ('cargo_van', 'Cargo Van',               100, 0),
  ('tanker',    'Tanker / Hazmat',          50, 0),
  ('hotshot',   'Hot Shot',                 50, 0),
  ('auto',      'Auto Carrier',             50, 0)
on conflict (category) do nothing;

-- ── loads ───────────────────────────────────────────────────
create table if not exists public.loads (
  id            uuid primary key default gen_random_uuid(),
  carrier_id    uuid references public.active_carriers(id) on delete cascade,
  truck_id      text,
  driver_code   text,
  broker_name   text,
  load_number   text,
  origin_city   text,
  origin_state  text,
  dest_city     text,
  dest_state    text,
  pickup_at     timestamptz,
  delivery_at   timestamptz,
  miles         int,
  rate_total    numeric(10,2),
  rate_per_mile numeric(6,2),
  pod_url       text,
  driver_name   text,
  origin        text,
  destination   text,
  rate          numeric(10,2),
  rpm           numeric(6,2),
  dispatch_fee  numeric(10,2),
  dispatch_pct  numeric(5,2),
  pickup_date   date,
  commodity     text,
  notes         text,
  status        text default 'booked',
  created_at    timestamptz not null default now()
);
alter table public.loads add column if not exists truck_id      text;
alter table public.loads add column if not exists driver_code   text;
alter table public.loads add column if not exists broker_name   text;
alter table public.loads add column if not exists load_number   text;
alter table public.loads add column if not exists origin_city   text;
alter table public.loads add column if not exists origin_state  text;
alter table public.loads add column if not exists dest_city     text;
alter table public.loads add column if not exists dest_state    text;
alter table public.loads add column if not exists pickup_at     timestamptz;
alter table public.loads add column if not exists delivery_at   timestamptz;
alter table public.loads add column if not exists miles         int;
alter table public.loads add column if not exists rate_total    numeric(10,2);
alter table public.loads add column if not exists rate_per_mile numeric(6,2);
alter table public.loads add column if not exists pod_url       text;
alter table public.loads add column if not exists driver_name   text;
alter table public.loads add column if not exists origin        text;
alter table public.loads add column if not exists destination   text;
alter table public.loads add column if not exists rate          numeric(10,2);
alter table public.loads add column if not exists rpm           numeric(6,2);
alter table public.loads add column if not exists dispatch_fee  numeric(10,2);
alter table public.loads add column if not exists dispatch_pct  numeric(5,2);
alter table public.loads add column if not exists pickup_date   date;
alter table public.loads add column if not exists commodity     text;
alter table public.loads add column if not exists notes         text;
alter table public.loads add column if not exists status        text default 'booked';
create index if not exists idx_loads_carrier on public.loads(carrier_id);
create index if not exists idx_loads_status  on public.loads(status);
create index if not exists idx_loads_pickup  on public.loads(pickup_at desc);

-- ── invoices ────────────────────────────────────────────────
create table if not exists public.invoices (
  id             uuid primary key default gen_random_uuid(),
  carrier_id     uuid references public.active_carriers(id) on delete cascade,
  load_id        uuid references public.loads(id) on delete set null,
  invoice_number text,
  amount         numeric(10,2),
  dispatch_fee   numeric(10,2),
  status         text default 'Unpaid',
  due_date       date,
  paid_at        timestamptz,
  notes          text,
  paid_date      date,
  created_at     timestamptz not null default now()
);
alter table public.invoices add column if not exists invoice_number text;
alter table public.invoices add column if not exists amount         numeric(10,2);
alter table public.invoices add column if not exists dispatch_fee   numeric(10,2);
alter table public.invoices add column if not exists status         text default 'Unpaid';
alter table public.invoices add column if not exists due_date       date;
alter table public.invoices add column if not exists paid_at        timestamptz;
alter table public.invoices add column if not exists notes          text;
alter table public.invoices add column if not exists paid_date      date;
create index if not exists idx_invoices_status  on public.invoices(status);
create index if not exists idx_invoices_carrier on public.invoices(carrier_id);

-- ── agent_log ───────────────────────────────────────────────
create table if not exists public.agent_log (
  id         bigserial primary key,
  agent      text not null,
  action     text,
  carrier_id uuid,
  payload    jsonb,
  result     text,
  error      text,
  ts         timestamptz not null default now()
);
alter table public.agent_log add column if not exists ts timestamptz not null default now();
create index if not exists idx_agent_log_agent_ts on public.agent_log(agent, ts desc);
create index if not exists idx_agent_log_carrier  on public.agent_log(carrier_id, ts desc);

-- ── RLS ─────────────────────────────────────────────────────
create table if not exists public.carrier_user_map (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  carrier_id uuid not null,
  role       text not null default 'owner',
  created_at timestamptz not null default now()
);

create or replace function public.current_carrier_id() returns text
language sql stable security definer as $$
  select carrier_id::text from public.carrier_user_map where user_id::text = auth.uid()::text limit 1
$$;

create or replace function public.is_admin() returns boolean
language sql stable as $$
  select coalesce((auth.jwt() ->> 'role') = 'admin', false)
$$;

alter table public.active_carriers     enable row level security;
alter table public.fleet_assets        enable row level security;
alter table public.truck_telemetry     enable row level security;
alter table public.drivers             enable row level security;
alter table public.driver_hos_status   enable row level security;
alter table public.eld_connections     enable row level security;
alter table public.insurance_compliance enable row level security;
alter table public.banking_accounts    enable row level security;
alter table public.signatures_audit    enable row level security;
alter table public.loads               enable row level security;
alter table public.invoices            enable row level security;
alter table public.leads               enable row level security;
alter table public.agent_log           enable row level security;
alter table public.carrier_user_map    enable row level security;

drop policy if exists carriers_read_own    on public.active_carriers;
drop policy if exists fleet_read_own       on public.fleet_assets;
drop policy if exists telemetry_read_own   on public.truck_telemetry;
drop policy if exists drivers_read_own     on public.drivers;
drop policy if exists hos_read_own         on public.driver_hos_status;
drop policy if exists eld_read_own         on public.eld_connections;
drop policy if exists insurance_read_own   on public.insurance_compliance;
drop policy if exists banking_admin_only   on public.banking_accounts;
drop policy if exists sig_read_own         on public.signatures_audit;
drop policy if exists loads_read_own       on public.loads;
drop policy if exists invoices_read_own    on public.invoices;
drop policy if exists leads_admin_only     on public.leads;
drop policy if exists agent_log_admin_only on public.agent_log;
drop policy if exists loads_insert         on public.loads;
drop policy if exists loads_update         on public.loads;
drop policy if exists loads_delete         on public.loads;
drop policy if exists invoices_insert      on public.invoices;
drop policy if exists invoices_update      on public.invoices;
drop policy if exists invoices_delete      on public.invoices;

create policy carriers_read_own    on public.active_carriers       for select using (id::text = public.current_carrier_id() or public.is_admin());
create policy fleet_read_own       on public.fleet_assets          for select using (carrier_id::text = public.current_carrier_id() or public.is_admin());
create policy telemetry_read_own   on public.truck_telemetry       for select using (carrier_id::text = public.current_carrier_id() or public.is_admin());
create policy drivers_read_own     on public.drivers               for select using (carrier_id::text = public.current_carrier_id() or public.is_admin());
create policy hos_read_own         on public.driver_hos_status     for select using (carrier_id::text = public.current_carrier_id() or public.is_admin());
create policy eld_read_own         on public.eld_connections       for select using (carrier_id::text = public.current_carrier_id() or public.is_admin());
create policy insurance_read_own   on public.insurance_compliance  for select using (carrier_id::text = public.current_carrier_id() or public.is_admin());
create policy banking_admin_only   on public.banking_accounts      for select using (public.is_admin());
create policy sig_read_own         on public.signatures_audit      for select using (carrier_id::text = public.current_carrier_id() or public.is_admin());
create policy loads_read_own       on public.loads                 for select using (carrier_id::text = public.current_carrier_id() or public.is_admin());
create policy invoices_read_own    on public.invoices              for select using (carrier_id::text = public.current_carrier_id() or public.is_admin());
create policy leads_admin_only     on public.leads                 for select using (public.is_admin());
create policy agent_log_admin_only on public.agent_log             for select using (public.is_admin());
create policy loads_insert         on public.loads                 for insert with check (true);
create policy loads_update         on public.loads                 for update using (true);
create policy loads_delete         on public.loads                 for delete using (true);
create policy invoices_insert      on public.invoices              for insert with check (true);
create policy invoices_update      on public.invoices              for update using (true);
create policy invoices_delete      on public.invoices              for delete using (true);

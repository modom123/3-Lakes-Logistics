-- Step 9: Row Level Security. Driver + telemetry + HOS + banking data
-- must never leak across carriers. Service role (backend) bypasses RLS;
-- anon + authenticated see only their own carrier rows.
--
-- Carrier scoping uses auth.uid() mapped through a link table. For the
-- dispatch admin (Commander) we issue tokens with a `role: admin` claim
-- that bypasses the carrier filter.

-- Map Supabase auth.users → active_carriers (carrier admin portal login)
create table if not exists public.carrier_user_map (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  carrier_id uuid not null references public.active_carriers(id) on delete cascade,
  role       text not null default 'owner',  -- owner | dispatcher | viewer
  created_at timestamptz not null default now()
);

-- Helper: resolve carrier_id for current jwt
create or replace function public.current_carrier_id() returns uuid
language sql stable security definer as $$
  select carrier_id from public.carrier_user_map where user_id = auth.uid() limit 1
$$;

-- Helper: is the current jwt the dispatch admin?
create or replace function public.is_admin() returns boolean
language sql stable as $$
  select coalesce((auth.jwt() ->> 'role') = 'admin', false)
$$;

-- Enable RLS
alter table public.active_carriers       enable row level security;
alter table public.fleet_assets          enable row level security;
alter table public.truck_telemetry       enable row level security;
alter table public.drivers               enable row level security;
alter table public.driver_hos_status     enable row level security;
alter table public.eld_connections       enable row level security;
alter table public.insurance_compliance  enable row level security;
alter table public.banking_accounts      enable row level security;
alter table public.signatures_audit      enable row level security;
alter table public.loads                 enable row level security;
alter table public.invoices              enable row level security;
alter table public.leads                 enable row level security;
alter table public.agent_log             enable row level security;
alter table public.carrier_user_map      enable row level security;

-- Generic "own carrier or admin" SELECT policy
create policy carriers_read_own on public.active_carriers
  for select using (id = public.current_carrier_id() or public.is_admin());

create policy fleet_read_own on public.fleet_assets
  for select using (carrier_id = public.current_carrier_id() or public.is_admin());

create policy telemetry_read_own on public.truck_telemetry
  for select using (carrier_id = public.current_carrier_id() or public.is_admin());

create policy drivers_read_own on public.drivers
  for select using (carrier_id = public.current_carrier_id() or public.is_admin());

create policy hos_read_own on public.driver_hos_status
  for select using (carrier_id = public.current_carrier_id() or public.is_admin());

create policy eld_read_own on public.eld_connections
  for select using (carrier_id = public.current_carrier_id() or public.is_admin());

create policy insurance_read_own on public.insurance_compliance
  for select using (carrier_id = public.current_carrier_id() or public.is_admin());

-- Banking: NEVER readable except by service role or admin
create policy banking_admin_only on public.banking_accounts
  for select using (public.is_admin());

create policy sig_read_own on public.signatures_audit
  for select using (carrier_id = public.current_carrier_id() or public.is_admin());

create policy loads_read_own on public.loads
  for select using (carrier_id = public.current_carrier_id() or public.is_admin());

create policy invoices_read_own on public.invoices
  for select using (carrier_id = public.current_carrier_id() or public.is_admin());

-- Leads are admin-only (prospecting is internal to the Commander)
create policy leads_admin_only on public.leads
  for select using (public.is_admin());

create policy agent_log_admin_only on public.agent_log
  for select using (public.is_admin());

-- All writes route through the FastAPI service role. Block direct client writes.
create policy no_client_inserts_carriers on public.active_carriers for insert with check (false);
create policy no_client_updates_carriers on public.active_carriers for update using (false);
-- (Repeat the same restrictive pattern for the other tables in production;
--  kept minimal here to stay readable.)

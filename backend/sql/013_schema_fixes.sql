-- Stage 5 step 101: Schema fixes for columns/tables the Stage 5 code
-- references but that weren't in migrations 001-012. Safe & additive —
-- every `alter` uses `if not exists` and every `create table` uses
-- `if not exists`, so this migration is idempotent.

-- ---- active_carriers: orbit reactivation signal
alter table public.active_carriers
  add column if not exists last_active_at timestamptz;
create index if not exists idx_carriers_last_active
  on public.active_carriers (last_active_at);

-- ---- drivers: Settler weekly_run filters on status
alter table public.drivers
  add column if not exists status text not null default 'active';
create index if not exists idx_drivers_status on public.drivers (status);

-- ---- insurance_compliance: Shield fmcsa_sync writes these
alter table public.insurance_compliance
  add column if not exists operating_status text,
  add column if not exists safety_rating    text;

-- ---- loads: Sonny + loadboard_scraper reference these
alter table public.loads
  add column if not exists source       text,
  add column if not exists ref          text,
  add column if not exists origin       text,
  add column if not exists destination  text,
  add column if not exists trailer_type text,
  add column if not exists weight_lbs   int,
  add column if not exists deadhead_mi  int,
  add column if not exists duration_h   numeric(5,2);
create index if not exists idx_loads_source on public.loads (source);
create index if not exists idx_loads_trailer on public.loads (trailer_type);

-- Broaden the status vocabulary — scrapers insert rows with status='open'
-- to mean "on the board, not yet matched"; atlas transitions to booked
-- on assignment. Existing `default 'booked'` is fine for manual inserts;
-- we just document the extended vocab here.
comment on column public.loads.status is
  'open | booked | dispatched | in_transit | delivered | pod_needed | closed';

-- ---- driver_deductions: Settler pulls per-week deductions
create table if not exists public.driver_deductions (
  id          uuid primary key default gen_random_uuid(),
  carrier_id  uuid references public.active_carriers(id) on delete cascade,
  driver_id   uuid references public.drivers(id) on delete cascade,
  kind        text not null,   -- fuel_advance | factoring_fee | chargeback | other
  amount      numeric(10,2) not null,
  period_end  date,
  note        text,
  created_at  timestamptz not null default now()
);
create index if not exists idx_deductions_driver_period
  on public.driver_deductions (driver_id, period_end);
alter table public.driver_deductions enable row level security;
create policy ddx_read_own on public.driver_deductions
  for select using (carrier_id = public.current_carrier_id() or public.is_admin());

-- ---- fleet_assets: Sonny match payload + HOS hints
alter table public.fleet_assets
  add column if not exists hos_hours_remaining numeric(5,2);

-- ---- Legacy plaintext credentials: deprecate but don't drop
comment on column public.eld_connections.eld_api_token is
  'DEPRECATED — write to eld_api_token_enc (Fernet). '
  'Left for rollback safety; null out once all clients are migrated.';
comment on column public.banking_accounts.account_token is
  'Stripe/Plaid token handle. Raw bank numbers live in '
  'bank_routing_enc / bank_account_enc (Fernet).';

-- ---- Sanity: stages vocabulary alignment on leads
-- Scout writes new|hot|warm|cold; dashboard kanban reads
-- new|hot|warm|cold|contacted|won|lost. Older rows may carry the
-- legacy new|contacted|engaged|qualified|converted|nurture|dead set.
-- No constraint change — text column accepts all. Column comment only.
comment on column public.leads.stage is
  'new | hot | warm | cold | contacted | engaged | qualified | '
  'converted | nurture | won | lost | dead';

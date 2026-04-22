-- Step 5-9 support tables: insurance_compliance (Shield), banking_accounts
-- (Settler), eld_connections (Motive/Samsara creds), signatures_audit
-- (e-sign evidence), founders_inventory (countdown), loads + invoices.

create table if not exists public.eld_connections (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid not null references public.active_carriers(id) on delete cascade,
  eld_provider    text not null,  -- motive | samsara | geotab | omnitracs
  eld_api_token   text,           -- encrypted in app layer before insert
  eld_account_id  text,
  status          text default 'pending',
  last_sync_at    timestamptz,
  created_at      timestamptz not null default now(),
  unique (carrier_id, eld_provider)
);

create table if not exists public.insurance_compliance (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid not null unique references public.active_carriers(id) on delete cascade,
  insurance_carrier  text,
  policy_number      text,
  policy_expiry      date,
  coi_url            text,
  bmc91_ack          boolean default false,
  mcs90_ack          boolean default false,
  safer_consent      boolean default false,
  csa_consent        boolean default false,
  clearinghouse_consent boolean default false,
  psp_consent        boolean default false,
  safety_light       text default 'yellow',  -- green | yellow | red
  last_checked_at    timestamptz,
  created_at         timestamptz not null default now()
);

create table if not exists public.banking_accounts (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid not null unique references public.active_carriers(id) on delete cascade,
  bank_routing_last4 text,
  bank_account_last4 text,
  account_token   text,            -- Stripe/Plaid token, not the raw number
  account_type    text,            -- checking | savings
  payee_name      text,
  w9_url          text,
  verified_at     timestamptz,
  created_at      timestamptz not null default now()
);

create table if not exists public.signatures_audit (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid references public.active_carriers(id) on delete cascade,
  doc_type        text,            -- dispatch_agreement | w9 | coi_upload | bmc91
  esign_name      text,
  ip              text,
  user_agent      text,
  pdf_hash        text,
  signed_at       timestamptz not null default now()
);

-- Founders inventory (drives the countdown table on index (7).html)
create table if not exists public.founders_inventory (
  category        text primary key,
  display_name    text,
  total           int not null,
  claimed         int not null default 0,
  reserved        int not null default 0
);

-- Keys must match FOUNDERS_CATEGORIES in index (7).html exactly.
insert into public.founders_inventory (category, display_name, total, claimed) values
  ('dry_van','Dry Van',300,0),
  ('reefer','Reefer',200,0),
  ('flatbed','Flatbed / Step Deck',150,0),
  ('box_truck','Box Truck 26'' (Non-CDL)',100,0),
  ('cargo_van','Cargo Van',100,0),
  ('tanker','Tanker / Hazmat',50,0),
  ('hotshot','Hot Shot',50,0),
  ('auto','Auto Carrier',50,0)
on conflict (category) do nothing;

-- Loads and invoices (referenced by the command center Dispatch + Invoices pages)
create table if not exists public.loads (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid references public.active_carriers(id) on delete cascade,
  truck_id        text,
  driver_code     text,
  broker_name     text,
  load_number     text,
  origin_city     text,
  origin_state    text(2),
  dest_city       text,
  dest_state      text(2),
  pickup_at       timestamptz,
  delivery_at     timestamptz,
  miles           int,
  rate_total      numeric(10,2),
  rate_per_mile   numeric(6,2),
  status          text default 'booked',
    -- booked | dispatched | in_transit | delivered | pod_needed | closed
  pod_url         text,
  created_at      timestamptz not null default now()
);

create index if not exists idx_loads_carrier on public.loads(carrier_id);
create index if not exists idx_loads_status on public.loads(status);
create index if not exists idx_loads_pickup on public.loads(pickup_at desc);

create table if not exists public.invoices (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid references public.active_carriers(id) on delete cascade,
  load_id         uuid references public.loads(id) on delete set null,
  invoice_number  text,
  amount          numeric(10,2),
  dispatch_fee    numeric(10,2),
  status          text default 'Unpaid',  -- Unpaid | Paid | Overdue
  due_date        date,
  paid_at         timestamptz,
  created_at      timestamptz not null default now()
);

create index if not exists idx_invoices_status on public.invoices(status);
create index if not exists idx_invoices_carrier on public.invoices(carrier_id);

-- Agent decision log (logging_service.py writes here)
create table if not exists public.agent_log (
  id              bigserial primary key,
  agent           text not null,
  action          text,
  carrier_id      uuid,
  payload         jsonb,
  result          text,
  error           text,
  ts              timestamptz not null default now()
);

create index if not exists idx_agent_log_agent_ts on public.agent_log(agent, ts desc);
create index if not exists idx_agent_log_carrier on public.agent_log(carrier_id, ts desc);

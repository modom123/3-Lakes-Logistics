-- Carrier Factoring Management Schema
-- Run in Supabase SQL editor

create table if not exists carrier_factoring (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid references carriers(id) on delete set null,
  carrier_name    text not null,
  carrier_mc      text,
  carrier_dot     text,
  carrier_email   text,

  factor_company  text not null,
  factor_contact  text,
  factor_email    text,
  factor_phone    text,
  factor_address  text,
  carrier_acct_at_factor text,
  payment_method  text default 'ACH',   -- ACH, Check, Wire, QuickPay
  remittance_email text,
  remittance_notes text,

  noa_status      text default 'pending',  -- pending, sent, signed, expired
  noa_signed_at   timestamptz,
  noa_document_id uuid references document_vault(id) on delete set null,
  noa_token       text,

  active          boolean default true,
  notes           text,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

create index if not exists idx_carrier_factoring_carrier on carrier_factoring(carrier_id);
create index if not exists idx_carrier_factoring_status on carrier_factoring(noa_status);
create index if not exists idx_carrier_factoring_active on carrier_factoring(active);

-- auto-update updated_at
create or replace function update_carrier_factoring_ts()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

drop trigger if exists trg_carrier_factoring_ts on carrier_factoring;
create trigger trg_carrier_factoring_ts
  before update on carrier_factoring
  for each row execute function update_carrier_factoring_ts();

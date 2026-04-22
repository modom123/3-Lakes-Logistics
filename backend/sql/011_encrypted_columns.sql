-- Stage 5 step 76: encrypted-at-rest columns for PII/secrets.
alter table public.eld_connections
  add column if not exists eld_api_token_enc text;

alter table public.banking_accounts
  add column if not exists bank_routing_enc  text,
  add column if not exists bank_account_enc  text,
  add column if not exists bank_account_mask text;

-- Once encrypted values are written, old plaintext columns should be nulled
-- and eventually dropped. Left intact here to allow rolling migration.
comment on column public.eld_connections.eld_api_token_enc
  is 'Fernet-encrypted via app.security.encrypt_str — never log';
comment on column public.banking_accounts.bank_routing_enc
  is 'Fernet-encrypted routing number — service role only';
comment on column public.banking_accounts.bank_account_enc
  is 'Fernet-encrypted account number — service role only';

-- Signatures_audit: store a signed PDF URL from Supabase Storage (step 78)
alter table public.signatures_audit
  add column if not exists pdf_url text;

-- KPI snapshots rollup (step 97)
create table if not exists public.kpi_snapshots (
  id uuid primary key default gen_random_uuid(),
  ts timestamptz not null default now(),
  carriers_active int,
  carriers_onboarding int,
  carriers_suspended int,
  loads_today int,
  gross_today numeric(12,2),
  leads_hot int,
  leads_warm int
);
create index if not exists kpi_ts_idx on public.kpi_snapshots (ts desc);

alter table public.kpi_snapshots enable row level security;
create policy kpi_admin on public.kpi_snapshots for select using (public.is_admin());

-- Patch leads table: add columns referenced by Eagle Eye UI and the API layer.
-- Safe to re-run (all use IF NOT EXISTS / DO NOTHING patterns).

-- city/state for map display in Eagle Eye lead table
alter table public.leads add column if not exists city  text;
alter table public.leads add column if not exists state text;

-- business_name: display-friendly alias that the API layer and Lead model use
alter table public.leads add column if not exists business_name text;

-- status: Eagle Eye pipeline status column (mirrors stage semantics)
-- Existing rows get their current stage value copied over.
alter table public.leads add column if not exists status text default 'new';
update public.leads set status = stage where status is null and stage is not null;

-- dot_age_days: pre-computed for the lead scorer so it doesn't need to recalculate
alter table public.leads add column if not exists dot_age_days int;

-- phone_number: alternate column name used by some scrapers
alter table public.leads add column if not exists phone_number text;

-- equipment_type (singular): used by Eagle Eye display alongside equipment_types[]
alter table public.leads add column if not exists equipment_type text;

-- Add missing INSERT/UPDATE/DELETE RLS policies for leads so the service role
-- can write leads without needing bypass (service role already bypasses RLS,
-- but these allow future anon-key-based internal writes if needed).
drop policy if exists leads_insert on public.leads;
drop policy if exists leads_update on public.leads;
drop policy if exists leads_delete on public.leads;

create policy leads_insert on public.leads for insert with check (true);
create policy leads_update on public.leads for update using (true);
create policy leads_delete on public.leads for delete using (true);

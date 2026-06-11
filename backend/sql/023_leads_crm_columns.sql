-- Migration 023 — leads columns the Lead CRM writes/reads but the table lacks.
--
-- The Eagle Eye Lead CRM PATCHes `notes`, `last_contact_at`, and `outreach_channel`
-- and reads them back. Without these columns every status change, note save, and
-- call log fails with "column does not exist", so the CRM appeared not to work.
-- `heat` persists the hot/warm/cold tag server-side (was localStorage-only).

alter table public.leads add column if not exists notes            text;
alter table public.leads add column if not exists last_contact_at  timestamptz;
alter table public.leads add column if not exists outreach_channel text;
alter table public.leads add column if not exists heat             text;

-- Backfill last_contact_at from the existing last_touch_at so the CRM's
-- "Last Contact" display and the summary's "contacted" detection agree.
update public.leads set last_contact_at = last_touch_at
  where last_contact_at is null and last_touch_at is not null;

-- 021 · Leads CRM columns
-- Columns the Eagle Eye CRM and the email_campaigner already write to but that
-- were never declared in a migration. Idempotent / safe to re-run.

-- When the lead was last contacted (call/email/meeting logged in the CRM).
alter table public.leads add column if not exists last_contact_at timestamptz;

-- Channel of the most recent outreach: call | email | sms.
alter table public.leads add column if not exists outreach_channel text;

-- Helpful for the Follow-ups Due queue and "Need 1st Touch" metrics.
create index if not exists idx_leads_next_touch    on public.leads (next_touch_at) where next_touch_at is not null;
create index if not exists idx_leads_last_contact   on public.leads (last_contact_at) where last_contact_at is not null;

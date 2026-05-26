-- ============================================================
-- Migration 019: Rate Confirmation Tracking
-- Adds columns to loads table so Eagle Eye and PWA can show
-- whether a rate confirmation has been sent to the carrier.
-- ============================================================

alter table public.loads add column if not exists rate_con_sent_at  timestamptz;
alter table public.loads add column if not exists rate_con_sent_to  text;   -- email address

create index if not exists idx_loads_rate_con
  on public.loads(rate_con_sent_at)
  where rate_con_sent_at is not null;

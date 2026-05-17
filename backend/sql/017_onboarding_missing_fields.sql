-- Migration 017: Add onboarding_missing_fields column to active_carriers
-- Required by routes_intake.py and routes_carriers.py to track incomplete onboarding submissions.
-- Run this against existing Supabase instances that were created before LIVE_SCHEMA_PART1 was updated.

alter table public.active_carriers
  add column if not exists onboarding_missing_fields text[];

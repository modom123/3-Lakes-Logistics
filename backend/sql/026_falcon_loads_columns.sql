-- Migration 026: Add FALCON-required columns to loads table
-- bol_url: stores signed URL for Bill of Lading document
-- pickup_confirmed_at: timestamped when carrier taps "Picked Up" in FALCON
-- weight_lbs: cargo weight in pounds (FALCON load details display)

ALTER TABLE loads
  ADD COLUMN IF NOT EXISTS bol_url              text,
  ADD COLUMN IF NOT EXISTS pickup_confirmed_at  timestamptz,
  ADD COLUMN IF NOT EXISTS weight_lbs           numeric;

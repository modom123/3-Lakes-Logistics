-- Add missing columns to light_vehicle_drivers that the maya intake agent writes.
-- Without these, the insert fails silently and no driver record is ever created.
-- Safe to re-run (all use IF NOT EXISTS).

-- platforms_opted_in: platforms the driver selected at signup (Curri, Roadie, etc.)
ALTER TABLE public.light_vehicle_drivers
  ADD COLUMN IF NOT EXISTS platforms_opted_in text[] DEFAULT '{}';

-- dob: date of birth — extracted by Stripe Identity after license scan
ALTER TABLE public.light_vehicle_drivers
  ADD COLUMN IF NOT EXISTS dob date;

-- activated_at: timestamp set by maya.approve_driver after MVR/Stripe clears
ALTER TABLE public.light_vehicle_drivers
  ADD COLUMN IF NOT EXISTS activated_at timestamptz;

-- Add onboarding_missing_fields column to track incomplete carrier profiles
ALTER TABLE active_carriers ADD COLUMN IF NOT EXISTS onboarding_missing_fields text[];

-- Index for filtering incomplete carriers in the ops dashboard
CREATE INDEX IF NOT EXISTS idx_carriers_status ON active_carriers(status);
CREATE INDEX IF NOT EXISTS idx_carriers_incomplete ON active_carriers(status) WHERE status = 'onboarding_incomplete';

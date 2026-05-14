-- Loads table extension — add load board integrations & rate confirmation fields
-- Idempotent: safe to run multiple times

ALTER TABLE loads ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual';  -- 'manual', 'dat', 'truckstop', 'email', etc.
ALTER TABLE loads ADD COLUMN IF NOT EXISTS source_id TEXT;  -- ID from external load board (e.g. DAT load ID)
ALTER TABLE loads ADD COLUMN IF NOT EXISTS equipment_type TEXT;  -- 'dry_van', 'flatbed', 'reefer', 'tanker', 'specialized'
ALTER TABLE loads ADD COLUMN IF NOT EXISTS gross_rate DECIMAL(10,2);  -- Before deductions/fuel advance
ALTER TABLE loads ADD COLUMN IF NOT EXISTS shipper_name TEXT;  -- Can differ from broker_name
ALTER TABLE loads ADD COLUMN IF NOT EXISTS shipper_phone TEXT;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS rate_confirmed_at TIMESTAMPTZ;  -- When rate con email received
ALTER TABLE loads ADD COLUMN IF NOT EXISTS rate_confirmation_notes TEXT;  -- Extracted from email

-- Indexes for frequent queries
CREATE INDEX IF NOT EXISTS idx_loads_source ON loads(source);
CREATE INDEX IF NOT EXISTS idx_loads_source_id ON loads(source_id);
CREATE INDEX IF NOT EXISTS idx_loads_equipment ON loads(equipment_type);
CREATE INDEX IF NOT EXISTS idx_loads_rate_confirmed ON loads(rate_confirmed_at);

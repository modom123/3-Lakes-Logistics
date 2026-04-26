-- 015_prospecting_phase3.sql
-- Extends the leads table with Phase 3 prospecting fields

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS lead_score         INT,
    ADD COLUMN IF NOT EXISTS first_name         TEXT,
    ADD COLUMN IF NOT EXISTS last_name          TEXT,
    ADD COLUMN IF NOT EXISTS home_state         TEXT,
    ADD COLUMN IF NOT EXISTS call_count         INT     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS owner_phone        TEXT,
    ADD COLUMN IF NOT EXISTS owner_email        TEXT,
    ADD COLUMN IF NOT EXISTS nurture_step       INT     DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_nurture_sent_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS carrier_id         UUID    REFERENCES active_carriers(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS vapi_call_id       TEXT,
    ADD COLUMN IF NOT EXISTS last_call_transcript       TEXT,
    ADD COLUMN IF NOT EXISTS last_call_recording_url    TEXT,
    ADD COLUMN IF NOT EXISTS social_signals     TEXT[];

-- Sync lead_score from score on write (score is the canonical column)
-- lead_score is an alias kept for API compatibility
CREATE OR REPLACE FUNCTION sync_lead_score()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.score IS NOT NULL AND NEW.lead_score IS NULL THEN
        NEW.lead_score := NEW.score;
    ELSIF NEW.lead_score IS NOT NULL AND NEW.score IS NULL THEN
        NEW.score := NEW.lead_score;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER trg_sync_lead_score
    BEFORE INSERT OR UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION sync_lead_score();

-- Indexes for new query patterns
CREATE INDEX IF NOT EXISTS idx_leads_nurture   ON leads(nurture_step) WHERE stage = 'nurture';
CREATE INDEX IF NOT EXISTS idx_leads_carrier   ON leads(carrier_id)   WHERE carrier_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leads_home_state ON leads(home_state)  WHERE home_state IS NOT NULL;

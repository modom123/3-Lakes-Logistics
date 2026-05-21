-- ─────────────────────────────────────────────────────────────────────────────
-- 024 · Carrier Brain — per-carrier relationship intelligence
-- Run in Supabase SQL editor.
-- ─────────────────────────────────────────────────────────────────────────────

-- Individual carrier memory — replaces generic patterns with carrier-specific intel
-- UNIQUE(carrier_id, memory_type): always 1 row per carrier+type, UPSERT-safe
CREATE TABLE IF NOT EXISTS carrier_brain (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  carrier_id        text        NOT NULL,
  carrier_name      text,
  memory_type       text        NOT NULL,   -- 'risk_profile' | 'call_history' | 'load_pattern' | 'relationship' | 'onboarding'
  memory_value      jsonb       NOT NULL DEFAULT '{}',
  confidence        numeric(4,3) DEFAULT 0.5  CHECK (confidence BETWEEN 0 AND 1),
  last_agent        text,                   -- which agent last wrote this memory
  interaction_count integer     DEFAULT 1,
  summary           text,
  created_at        timestamptz DEFAULT now(),
  updated_at        timestamptz DEFAULT now(),
  UNIQUE (carrier_id, memory_type)
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_carrier_brain_carrier   ON carrier_brain (carrier_id);
CREATE INDEX IF NOT EXISTS idx_carrier_brain_type      ON carrier_brain (memory_type);
CREATE INDEX IF NOT EXISTS idx_carrier_brain_updated   ON carrier_brain (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_carrier_brain_confidence ON carrier_brain (confidence DESC);

-- RLS: service-role only (Eagle Eye backend reads/writes; no public access)
ALTER TABLE carrier_brain ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS carrier_brain_service_only ON carrier_brain;
CREATE POLICY carrier_brain_service_only ON carrier_brain
  USING (auth.role() = 'service_role');

-- Trigger: auto-update updated_at on any row change
CREATE OR REPLACE FUNCTION set_carrier_brain_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

DROP TRIGGER IF EXISTS trg_carrier_brain_updated_at ON carrier_brain;
CREATE TRIGGER trg_carrier_brain_updated_at
  BEFORE UPDATE ON carrier_brain
  FOR EACH ROW EXECUTE FUNCTION set_carrier_brain_updated_at();

-- Seed: memory type reference comment (informational — not a real row)
-- memory_type catalogue:
--   risk_profile    : Winston writes — risk reason, priority, inactivity window
--   call_history    : Vance writes   — total calls, connect rate, last call status
--   load_pattern    : auto-derived   — load count, avg rate, preferred lanes
--   relationship    : Isabella writes — campaign touches, last message sent
--   onboarding      : manual/system  — onboarding step, blocking issues

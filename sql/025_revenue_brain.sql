-- ─────────────────────────────────────────────────────────────────────────────
-- 025 · Revenue Brain — financial pattern & period intelligence
-- Run in Supabase SQL editor.
-- ─────────────────────────────────────────────────────────────────────────────

-- Period-based financial memory — Sofia and Eleanor write, Victoria + Commander read
-- UNIQUE(period_key, metric_key): 1 row per period+metric, UPSERT-safe
CREATE TABLE IF NOT EXISTS revenue_brain (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  period_key   text        NOT NULL,   -- 'all_time' | '2026-05' | '2026-Q2' | 'rolling_30d'
  metric_key   text        NOT NULL,   -- 'ar_outstanding' | 'collection_rate' | 'missing_invoices' | 'monthly_revenue' | 'load_revenue' | 'plan_mix'
  metric_value jsonb       NOT NULL DEFAULT '{}',
  confidence   numeric(4,3) DEFAULT 0.5  CHECK (confidence BETWEEN 0 AND 1),
  source_agent text,
  summary      text,
  created_at   timestamptz DEFAULT now(),
  updated_at   timestamptz DEFAULT now(),
  UNIQUE (period_key, metric_key)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_revenue_brain_period     ON revenue_brain (period_key);
CREATE INDEX IF NOT EXISTS idx_revenue_brain_metric     ON revenue_brain (metric_key);
CREATE INDEX IF NOT EXISTS idx_revenue_brain_updated    ON revenue_brain (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_revenue_brain_confidence ON revenue_brain (confidence DESC);

-- RLS
ALTER TABLE revenue_brain ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS revenue_brain_service_only ON revenue_brain;
CREATE POLICY revenue_brain_service_only ON revenue_brain
  USING (auth.role() = 'service_role');

-- Trigger: auto-update updated_at
CREATE OR REPLACE FUNCTION set_revenue_brain_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

DROP TRIGGER IF EXISTS trg_revenue_brain_updated_at ON revenue_brain;
CREATE TRIGGER trg_revenue_brain_updated_at
  BEFORE UPDATE ON revenue_brain
  FOR EACH ROW EXECUTE FUNCTION set_revenue_brain_updated_at();

-- Seed baseline financial context so the brain starts with a reference point
INSERT INTO revenue_brain (period_key, metric_key, metric_value, confidence, source_agent, summary)
VALUES
  ('all_time', 'ar_outstanding',   '{"amount": 0, "overdue_count": 0}', 0.1, 'system', 'Baseline AR — no data yet'),
  ('all_time', 'collection_rate',  '{"rate_pct": 0, "sample_size": 0}', 0.1, 'system', 'Baseline collection rate — no data yet'),
  ('all_time', 'missing_invoices', '{"count": 0, "load_ids": []}',       0.1, 'system', 'Baseline missing invoices — no data yet')
ON CONFLICT (period_key, metric_key) DO NOTHING;

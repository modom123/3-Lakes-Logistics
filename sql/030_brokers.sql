-- ─────────────────────────────────────────────────────────────────────────────
-- 030 · Broker Registry — broker onboarding, EDI integration, scorecards
-- Run in Supabase SQL editor.
-- ─────────────────────────────────────────────────────────────────────────────

-- ── Core broker table ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS brokers (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  mc_number             text        UNIQUE NOT NULL,
  dot_number            text,
  company_name          text        NOT NULL,
  dba_name              text,
  contact_name          text,
  contact_email         text,
  contact_phone         text,
  address               text,
  city                  text,
  state                 text,
  zip                   text,

  -- Financial terms
  payment_terms         text        DEFAULT 'Net-30',
  quick_pay_discount_pct numeric(5,2),
  factoring_allowed     boolean     DEFAULT true,
  cargo_liability_minimum numeric(12,2),

  -- Integration config
  api_type              text        DEFAULT 'manual',   -- 'edi' | 'rest' | 'manual'
  edi_partner_id        text,                           -- EDI ISA06 sender ID
  edi_qualifier         text,                           -- EDI ISA05 qualifier
  rest_endpoint         text,
  rest_api_key_enc      text,                           -- encrypted at rest

  -- Status & scoring
  status                text        NOT NULL DEFAULT 'pending',
  -- pending | active | suspended | blacklisted
  scorecard_score       numeric(4,1),
  avg_pay_days          numeric(5,1),
  on_time_pay_pct       numeric(5,2),
  dispute_rate_pct      numeric(5,2),
  total_loads           integer     DEFAULT 0,
  total_revenue         numeric(15,2) DEFAULT 0,
  last_load_at          timestamptz,

  notes                 text,
  onboarded_at          timestamptz,
  created_at            timestamptz DEFAULT now(),
  updated_at            timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_brokers_mc         ON brokers (mc_number);
CREATE INDEX IF NOT EXISTS idx_brokers_status     ON brokers (status);
CREATE INDEX IF NOT EXISTS idx_brokers_score      ON brokers (scorecard_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_brokers_updated    ON brokers (updated_at DESC);

-- ── Broker agreements (links broker to vault document + contract) ─────────────
CREATE TABLE IF NOT EXISTS broker_agreements (
  id              uuid  PRIMARY KEY DEFAULT gen_random_uuid(),
  broker_id       uuid  NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
  doc_id          uuid,               -- document_vault.id
  contract_id     uuid,               -- contracts.id
  agreement_type  text  DEFAULT 'broker_carrier_agreement',
  effective_date  date,
  expiration_date date,
  auto_renew      boolean DEFAULT false,
  status          text  DEFAULT 'active',  -- active | expired | superseded
  created_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_broker_agreements_broker ON broker_agreements (broker_id);
CREATE INDEX IF NOT EXISTS idx_broker_agreements_expiry ON broker_agreements (expiration_date);

-- ── EDI transaction log ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS broker_edi_log (
  id              uuid  PRIMARY KEY DEFAULT gen_random_uuid(),
  broker_id       uuid  REFERENCES brokers(id) ON DELETE SET NULL,
  direction       text  NOT NULL,          -- 'inbound' | 'outbound'
  transaction_set text  NOT NULL,          -- '204' | '990' | '214' | '210'
  interchange_id  text,
  load_number     text,
  contract_id     uuid,
  raw_edi         text,
  parsed_data     jsonb,
  status          text  DEFAULT 'received',
  -- inbound:  received | processed | failed
  -- outbound: queued   | sent      | acked | failed
  error_detail    text,
  created_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_edi_log_broker  ON broker_edi_log (broker_id);
CREATE INDEX IF NOT EXISTS idx_edi_log_ts      ON broker_edi_log (transaction_set);
CREATE INDEX IF NOT EXISTS idx_edi_log_status  ON broker_edi_log (status);
CREATE INDEX IF NOT EXISTS idx_edi_log_load    ON broker_edi_log (load_number);
CREATE INDEX IF NOT EXISTS idx_edi_log_created ON broker_edi_log (created_at DESC);

-- ── Auto-update updated_at ────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_brokers_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

DROP TRIGGER IF EXISTS trg_brokers_updated_at ON brokers;
CREATE TRIGGER trg_brokers_updated_at
  BEFORE UPDATE ON brokers
  FOR EACH ROW EXECUTE FUNCTION set_brokers_updated_at();

-- ── RLS: service-role only ─────────────────────────────────────────────────────
ALTER TABLE brokers           ENABLE ROW LEVEL SECURITY;
ALTER TABLE broker_agreements ENABLE ROW LEVEL SECURITY;
ALTER TABLE broker_edi_log    ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS brokers_service_only           ON brokers;
DROP POLICY IF EXISTS broker_agreements_service_only ON broker_agreements;
DROP POLICY IF EXISTS broker_edi_log_service_only    ON broker_edi_log;

CREATE POLICY brokers_service_only           ON brokers           USING (auth.role() = 'service_role');
CREATE POLICY broker_agreements_service_only ON broker_agreements USING (auth.role() = 'service_role');
CREATE POLICY broker_edi_log_service_only    ON broker_edi_log    USING (auth.role() = 'service_role');

-- ── Realtime (Eagle Eye live updates) ─────────────────────────────────────────
ALTER PUBLICATION supabase_realtime ADD TABLE brokers;
ALTER PUBLICATION supabase_realtime ADD TABLE broker_edi_log;

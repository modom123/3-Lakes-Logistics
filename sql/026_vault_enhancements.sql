-- ─────────────────────────────────────────────────────────────────────────────
-- 026 · Document Vault Enhancements — send tracking, notes, send history log
-- ─────────────────────────────────────────────────────────────────────────────

-- Extend document_vault with send tracking and notes
ALTER TABLE document_vault ADD COLUMN IF NOT EXISTS sent_count   integer     DEFAULT 0;
ALTER TABLE document_vault ADD COLUMN IF NOT EXISTS last_sent_at timestamptz;
ALTER TABLE document_vault ADD COLUMN IF NOT EXISTS last_sent_to text;
ALTER TABLE document_vault ADD COLUMN IF NOT EXISTS notes        text;
ALTER TABLE document_vault ADD COLUMN IF NOT EXISTS load_number  text;
ALTER TABLE document_vault ADD COLUMN IF NOT EXISTS bucket       text        DEFAULT 'documents';

-- vault_sends: full send history (one row per email sent)
CREATE TABLE IF NOT EXISTS vault_sends (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid        NOT NULL,
  sent_to     text        NOT NULL,
  sent_by     text        DEFAULT 'commander',
  subject     text,
  message     text,
  sent_at     timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vault_sends_doc  ON vault_sends (document_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_vault_sends_time ON vault_sends (sent_at DESC);

-- RLS
ALTER TABLE vault_sends ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS vault_sends_service_only ON vault_sends;
CREATE POLICY vault_sends_service_only ON vault_sends
  USING (auth.role() = 'service_role');

-- Index on load_number for cross-referencing
CREATE INDEX IF NOT EXISTS idx_document_vault_load ON document_vault (load_number) WHERE load_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_document_vault_carrier ON document_vault (carrier_id) WHERE carrier_id IS NOT NULL;

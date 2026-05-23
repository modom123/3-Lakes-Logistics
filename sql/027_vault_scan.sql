-- ─────────────────────────────────────────────────────────────────────────────
-- 027 · Vault Document Scanning — extracted data storage
-- ─────────────────────────────────────────────────────────────────────────────

-- Add extraction columns to document_vault
ALTER TABLE document_vault ADD COLUMN IF NOT EXISTS extracted_data  jsonb;
ALTER TABLE document_vault ADD COLUMN IF NOT EXISTS extract_confidence numeric(4,3);
ALTER TABLE document_vault ADD COLUMN IF NOT EXISTS extract_warnings  text[];
ALTER TABLE document_vault ADD COLUMN IF NOT EXISTS extracted_at     timestamptz;
ALTER TABLE document_vault ADD COLUMN IF NOT EXISTS extract_method   text; -- 'pdf_text' | 'claude_vision' | 'manual'

-- Fast lookup for scanned/unscanned docs
CREATE INDEX IF NOT EXISTS idx_vault_extracted ON document_vault (extracted_at) WHERE extracted_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_vault_unscanned  ON document_vault (uploaded_at DESC) WHERE extracted_at IS NULL AND doc_type != 'folder';

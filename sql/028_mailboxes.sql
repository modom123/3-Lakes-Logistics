-- ─────────────────────────────────────────────────────────────────────────────
-- 028 · Mailbox Emails — unified inbox for all 5 Hostinger mailboxes
-- Mailboxes: loads@, sales@, info@, mark@, cece@ @3lakeslogistics.com
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mailbox_emails (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  mailbox          text        NOT NULL,       -- 'loads' | 'sales' | 'info' | 'mark' | 'cece'
  direction        text        NOT NULL DEFAULT 'inbound',  -- 'inbound' | 'outbound'
  message_id       text,                       -- SMTP Message-ID header (for dedup + threading)
  thread_id        text,                       -- In-Reply-To / References header
  from_address     text        NOT NULL,
  to_addresses     text[]      DEFAULT '{}',
  cc_addresses     text[]      DEFAULT '{}',
  subject          text,
  body_text        text,
  body_html        text,
  attachment_count integer     DEFAULT 0,
  attachments      jsonb       DEFAULT '[]'::jsonb,  -- [{name, content_type, size_kb, vault_doc_id?}]
  is_read          boolean     DEFAULT false,
  is_starred       boolean     DEFAULT false,
  status           text        DEFAULT 'received',   -- received | archived | error
  processed_as     text,                       -- rate_con | bol | pod | general
  load_id          uuid,
  carrier_id       uuid,
  extracted_data   jsonb,
  imap_uid         bigint,                     -- IMAP UID for reference
  received_at      timestamptz NOT NULL DEFAULT now(),
  sent_at          timestamptz,
  created_at       timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mailbox_emails_mailbox  ON mailbox_emails (mailbox, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_mailbox_emails_unread   ON mailbox_emails (mailbox, received_at DESC) WHERE is_read = false;
CREATE INDEX IF NOT EXISTS idx_mailbox_emails_msgid    ON mailbox_emails (message_id) WHERE message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mailbox_emails_all      ON mailbox_emails (received_at DESC);

ALTER TABLE mailbox_emails ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mailbox_emails_service_only ON mailbox_emails;
CREATE POLICY mailbox_emails_service_only ON mailbox_emails
  USING (auth.role() = 'service_role');

-- Migration 022 — CRM contacts (executive office "My CRM" tab) persistence.
--
-- Backs the per-office contact book (Mark = 'mark', CC Gulley = 'cece') so
-- contacts, pipeline stages, and activity timelines survive across browsers
-- and devices instead of living only in localStorage.

CREATE TABLE IF NOT EXISTS crm_contacts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner          TEXT NOT NULL DEFAULT 'mark',     -- which office owns the contact
    name           TEXT NOT NULL,
    company        TEXT,
    phone          TEXT,
    email          TEXT,
    type           TEXT,                              -- Broker | Carrier | Customer | …
    priority       TEXT DEFAULT 'none',               -- hot | warm | cold | none
    pipeline_stage TEXT,                              -- New Lead | Contacted | … | Won | Lost
    deal_value     NUMERIC,
    linkedin       TEXT,
    last_contacted TIMESTAMPTZ,
    notes          TEXT,
    activities     JSONB NOT NULL DEFAULT '[]'::jsonb, -- [{id,type,note,ts}]
    source_lead_id TEXT,                              -- provenance when pulled from a lead
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crm_contacts_owner ON crm_contacts (owner);
CREATE INDEX IF NOT EXISTS idx_crm_contacts_stage ON crm_contacts (owner, pipeline_stage);

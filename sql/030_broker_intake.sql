-- Migration 030: brokers table + welcome_emails audit log
-- Supports broker self-service signup and auto-registration via CLM scan

CREATE TABLE IF NOT EXISTS brokers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    broker_mc       TEXT UNIQUE,
    broker_name     TEXT NOT NULL,
    contact_name    TEXT,
    email           TEXT,
    phone           TEXT,
    address         TEXT,
    dot_number      TEXT,
    payment_terms   TEXT DEFAULT 'Net-30',
    factoring_allowed BOOLEAN DEFAULT TRUE,
    status          TEXT NOT NULL DEFAULT 'active',  -- active | suspended | blacklisted
    source          TEXT DEFAULT 'manual',            -- manual | clm_scan | intake_form
    onboarding_sent BOOLEAN DEFAULT FALSE,
    welcome_sent_at TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_brokers_mc     ON brokers(broker_mc);
CREATE INDEX IF NOT EXISTS idx_brokers_email  ON brokers(email);
CREATE INDEX IF NOT EXISTS idx_brokers_status ON brokers(status);

-- Track every outbound onboarding/welcome email sent to a broker
CREATE TABLE IF NOT EXISTS broker_welcome_emails (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    broker_id   UUID REFERENCES brokers(id) ON DELETE CASCADE,
    broker_mc   TEXT,
    email       TEXT NOT NULL,
    subject     TEXT,
    trigger     TEXT DEFAULT 'intake',  -- intake | clm_scan | manual
    sent_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_broker_welcome_broker ON broker_welcome_emails(broker_id);

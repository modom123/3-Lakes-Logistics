-- ============================================================
-- 3 Lakes Logistics — Shipper Portal Schema
-- ============================================================

-- Enable pgcrypto if not already enabled (for gen_random_bytes)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ────────────────────────────────────────────────────────────
-- shippers
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shippers (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name     TEXT NOT NULL,
    email            TEXT NOT NULL UNIQUE,
    phone            TEXT,
    address          TEXT,
    city             TEXT,
    state            TEXT,
    zip              TEXT,
    contact_name     TEXT,
    password_hash    TEXT NOT NULL,
    api_key          TEXT UNIQUE DEFAULT encode(gen_random_bytes(32), 'hex'),
    webhook_url      TEXT,
    webhook_secret   TEXT DEFAULT encode(gen_random_bytes(16), 'hex'),
    webhook_events   TEXT[] DEFAULT ARRAY['load.dispatched','load.delivered','load.invoiced'],
    status           TEXT NOT NULL DEFAULT 'active',
    credit_limit     NUMERIC DEFAULT 50000,
    payment_terms    INTEGER DEFAULT 30,
    total_loads      INTEGER DEFAULT 0,
    total_spend      NUMERIC DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ────────────────────────────────────────────────────────────
-- shipper_loads
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shipper_loads (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shipper_id           UUID NOT NULL REFERENCES shippers(id) ON DELETE CASCADE,
    load_id              UUID REFERENCES loads(id) ON DELETE SET NULL,
    tracking_token       TEXT UNIQUE DEFAULT encode(gen_random_bytes(16), 'hex'),

    -- Origin
    origin_address       TEXT,
    origin_city          TEXT,
    origin_state         TEXT,
    origin_zip           TEXT,
    origin_contact       TEXT,
    origin_phone         TEXT,
    pickup_date          DATE,
    pickup_window_start  TEXT,
    pickup_window_end    TEXT,

    -- Destination
    dest_address         TEXT,
    dest_city            TEXT,
    dest_state           TEXT,
    dest_zip             TEXT,
    dest_contact         TEXT,
    dest_phone           TEXT,
    delivery_date        DATE,
    delivery_window_start TEXT,
    delivery_window_end  TEXT,

    -- Freight info
    commodity            TEXT,
    weight_lbs           NUMERIC,
    length_ft            NUMERIC,
    width_ft             NUMERIC,
    height_ft            NUMERIC,
    pallets              INTEGER,
    load_type            TEXT DEFAULT 'dry_van',
    hazmat               BOOLEAN DEFAULT false,
    hazmat_class         TEXT,
    temp_controlled      BOOLEAN DEFAULT false,
    temp_min_f           NUMERIC,
    temp_max_f           NUMERIC,
    stackable            BOOLEAN DEFAULT true,
    special_instructions TEXT,

    -- Pricing
    quoted_miles         NUMERIC,
    base_rate            NUMERIC,
    fuel_surcharge       NUMERIC,
    accessorial_fees     NUMERIC DEFAULT 0,
    total_rate           NUMERIC,
    rate_per_mile        NUMERIC,

    -- Status
    status               TEXT NOT NULL DEFAULT 'quote',

    -- Invoice
    invoice_number       TEXT,
    invoice_amount       NUMERIC,
    invoice_date         DATE,
    invoice_due_date     DATE,
    invoice_paid         BOOLEAN DEFAULT false,
    invoice_paid_date    DATE,

    -- Live tracking
    current_lat          NUMERIC,
    current_lng          NUMERIC,
    current_city         TEXT,
    current_state        TEXT,
    last_update          TIMESTAMPTZ,
    eta                  TIMESTAMPTZ,

    -- Documents
    bol_url              TEXT,
    pod_url              TEXT,

    -- Notes
    internal_notes       TEXT,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ────────────────────────────────────────────────────────────
-- shipper_sessions
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shipper_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shipper_id  UUID NOT NULL REFERENCES shippers(id) ON DELETE CASCADE,
    token       TEXT NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    ip_address  TEXT,
    user_agent  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ────────────────────────────────────────────────────────────
-- shipper_webhook_log
-- ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shipper_webhook_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shipper_id    UUID NOT NULL REFERENCES shippers(id) ON DELETE CASCADE,
    event_type    TEXT,
    payload       JSONB,
    http_status   INTEGER,
    response_body TEXT,
    delivered     BOOLEAN DEFAULT false,
    attempts      INTEGER DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ────────────────────────────────────────────────────────────
-- Indexes
-- ────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_shipper_loads_shipper_id     ON shipper_loads(shipper_id);
CREATE INDEX IF NOT EXISTS idx_shipper_loads_tracking_token ON shipper_loads(tracking_token);
CREATE INDEX IF NOT EXISTS idx_shipper_loads_status         ON shipper_loads(status);
CREATE INDEX IF NOT EXISTS idx_shipper_sessions_token       ON shipper_sessions(token);

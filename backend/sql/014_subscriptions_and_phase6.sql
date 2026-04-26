-- 014_subscriptions_and_phase6.sql
-- Carrier subscription plans, ELD telemetry additions, active_drivers table

-- ── Carrier Subscriptions ─────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS carrier_subscriptions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    carrier_id              UUID NOT NULL REFERENCES active_carriers(id) ON DELETE CASCADE,

    plan                    TEXT NOT NULL DEFAULT 'standard_5pct'
                                CHECK (plan IN ('standard_5pct','premium_8pct','full_service_10pct','enterprise')),
    status                  TEXT NOT NULL DEFAULT 'trial'
                                CHECK (status IN ('trial','active','past_due','cancelled','suspended')),

    dispatch_pct            NUMERIC(4,2) DEFAULT 5.00,
    monthly_min             NUMERIC(10,2) DEFAULT 0,

    stripe_customer_id      TEXT,
    stripe_subscription_id  TEXT,

    activated_at            TIMESTAMPTZ,
    cancelled_at            TIMESTAMPTZ,
    cancel_reason           TEXT,
    trial_ends_at           TIMESTAMPTZ DEFAULT (now() + INTERVAL '14 days'),

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (carrier_id)
);

CREATE INDEX IF NOT EXISTS idx_carrier_subs_status  ON carrier_subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_carrier_subs_plan    ON carrier_subscriptions(plan);

CREATE OR REPLACE TRIGGER trg_carrier_subs_updated_at
    BEFORE UPDATE ON carrier_subscriptions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE carrier_subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY carrier_subs_service ON carrier_subscriptions
    USING (auth.role() = 'service_role');

CREATE POLICY carrier_subs_read ON carrier_subscriptions
    FOR SELECT USING (auth.role() = 'authenticated');


-- ── Active Drivers ────────────────────────────────────────────────────────────
-- A lightweight driver roster table used by pulse.py fleet_wellness()

CREATE TABLE IF NOT EXISTS active_drivers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    carrier_id      UUID REFERENCES active_carriers(id) ON DELETE SET NULL,
    driver_name     TEXT,
    driver_code     TEXT,
    phone           TEXT,
    email           TEXT,
    license_state   TEXT,
    equipment_type  TEXT DEFAULT 'dry_van',
    status          TEXT DEFAULT 'active'
                        CHECK (status IN ('active','inactive','on_load','suspended')),
    eld_provider    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_active_drivers_carrier ON active_drivers(carrier_id);
CREATE INDEX IF NOT EXISTS idx_active_drivers_status  ON active_drivers(status);

CREATE OR REPLACE TRIGGER trg_active_drivers_updated_at
    BEFORE UPDATE ON active_drivers
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

ALTER TABLE active_drivers ENABLE ROW LEVEL SECURITY;

CREATE POLICY active_drivers_service ON active_drivers
    USING (auth.role() = 'service_role');

CREATE POLICY active_drivers_read ON active_drivers
    FOR SELECT USING (auth.role() = 'authenticated');


-- ── Telemetry schema additions ────────────────────────────────────────────────
-- Add columns needed by the enhanced motive_webhook.py handler

ALTER TABLE truck_telemetry
    ADD COLUMN IF NOT EXISTS driver_id     UUID,
    ADD COLUMN IF NOT EXISTS harsh_brake   BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS harsh_accel   BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS idle_minutes  NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS event_severity TEXT CHECK (event_severity IN ('low','medium','high'));

CREATE INDEX IF NOT EXISTS idx_telemetry_driver   ON truck_telemetry(driver_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_created  ON truck_telemetry(created_at DESC);


-- ── HOS status additions ──────────────────────────────────────────────────────

ALTER TABLE driver_hos_status
    ADD COLUMN IF NOT EXISTS driver_id UUID;

CREATE INDEX IF NOT EXISTS idx_hos_driver ON driver_hos_status(driver_id);


-- ── Loads: scheduled_delivery column (for on-time calculation) ────────────────

ALTER TABLE loads
    ADD COLUMN IF NOT EXISTS scheduled_delivery TIMESTAMPTZ;


-- ── Revenue KPI view (for Phase 6 subscription_kpis endpoint) ────────────────

CREATE OR REPLACE VIEW subscription_kpis_view AS
SELECT
    COUNT(*) FILTER (WHERE cs.status = 'active')                AS active_carriers,
    COUNT(*) FILTER (WHERE cs.status = 'trial')                 AS trial_carriers,
    COUNT(*) FILTER (WHERE cs.status = 'cancelled')             AS churned_carriers,
    COALESCE(SUM(cs.monthly_min) FILTER (WHERE cs.status='active'), 0) AS mrr,
    COALESCE(SUM(cs.monthly_min) FILTER (WHERE cs.status='active'), 0) * 12 AS arr,
    COUNT(*) FILTER (WHERE cs.plan = 'standard_5pct')           AS plan_standard,
    COUNT(*) FILTER (WHERE cs.plan = 'premium_8pct')            AS plan_premium,
    COUNT(*) FILTER (WHERE cs.plan = 'full_service_10pct')      AS plan_full_service,
    COUNT(*) FILTER (WHERE cs.plan = 'enterprise')              AS plan_enterprise
FROM carrier_subscriptions cs;

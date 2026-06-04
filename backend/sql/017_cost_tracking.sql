-- 017_cost_tracking.sql
-- IEBC Cost Tracking System — API usage costs, subscriptions, budgets, reports
-- Tracks Anthropic, Bland AI, Twilio, Google, Stripe, Checkr, etc.

-- ── cost_entries ──────────────────────────────────────────────────────────────
-- One row per billable API call or batch. Written by cost_tracking.tracker.

CREATE TABLE IF NOT EXISTS cost_entries (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service      TEXT        NOT NULL,           -- 'anthropic', 'bland_ai', 'twilio', 'stripe', …
    category     TEXT        NOT NULL,           -- 'ai_llm' | 'communications' | 'infrastructure' | 'payments' | 'data' | 'compliance'
    cost_usd     NUMERIC(14, 6) NOT NULL,
    units        NUMERIC(14, 4),                 -- tokens, minutes, calls, images, etc.
    unit_type    TEXT,                           -- 'tokens' | 'minutes' | 'sms' | 'calls' | 'api_calls' | 'emails' | 'images' | 'checks' | 'usd_charged'
    description  TEXT,
    metadata     JSONB        NOT NULL DEFAULT '{}',
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cost_entries_service     ON cost_entries (service);
CREATE INDEX IF NOT EXISTS idx_cost_entries_category    ON cost_entries (category);
CREATE INDEX IF NOT EXISTS idx_cost_entries_recorded_at ON cost_entries (recorded_at DESC);

-- ── cost_subscriptions ────────────────────────────────────────────────────────
-- Fixed recurring platform costs (Supabase, Render, Vercel, Adobe Sign, DAT…)

CREATE TABLE IF NOT EXISTS cost_subscriptions (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service           TEXT        NOT NULL UNIQUE,
    plan_name         TEXT,
    billing_cycle     TEXT        NOT NULL DEFAULT 'monthly',  -- 'monthly' | 'annual' | 'usage'
    amount_usd        NUMERIC(10, 2) NOT NULL DEFAULT 0,
    next_billing_date DATE,
    active            BOOLEAN     NOT NULL DEFAULT TRUE,
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed known subscriptions
INSERT INTO cost_subscriptions (service, plan_name, billing_cycle, amount_usd, active) VALUES
    ('supabase',  'Pro',            'monthly', 25.00,  TRUE),
    ('render',    'Standard',       'monthly', 25.00,  TRUE),
    ('vercel',    'Pro',            'monthly', 20.00,  TRUE),
    ('airtable',  'Pro',            'monthly', 20.00,  TRUE),
    ('adobe_sign','Business',       'monthly', 34.99,  TRUE),
    ('postmark',  '10K/mo',         'monthly', 15.00,  TRUE),
    ('sendgrid',  'Essentials',     'monthly', 19.95,  TRUE),
    ('firebase',  'Blaze',          'monthly', 25.00,  TRUE),
    ('dat',       'Load Board',     'monthly', 149.00, TRUE),
    ('anthropic', 'API (usage)',    'usage',   0.00,   TRUE),
    ('twilio',    'Pay-as-you-go',  'usage',   0.00,   TRUE),
    ('bland_ai',  'Pay-as-you-go',  'usage',   0.00,   TRUE),
    ('openrouter','Pay-as-you-go',  'usage',   0.00,   TRUE),
    ('checkr',    'Pay-per-check',  'usage',   0.00,   TRUE),
    ('google_maps','Maps Platform', 'usage',   0.00,   TRUE),
    ('google_vision','Vision API',  'usage',   0.00,   TRUE),
    ('stripe',    'Payments',       'usage',   0.00,   TRUE)
ON CONFLICT (service) DO NOTHING;

-- ── cost_budgets ──────────────────────────────────────────────────────────────
-- Monthly spend caps per service or category. IEBC monitor checks daily.

CREATE TABLE IF NOT EXISTS cost_budgets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service             TEXT,                       -- NULL for category-level budget
    category            TEXT,
    monthly_budget_usd  NUMERIC(10, 2) NOT NULL,
    alert_threshold_pct INTEGER        NOT NULL DEFAULT 80,
    active              BOOLEAN        NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

-- Seed sensible default budgets
INSERT INTO cost_budgets (service, category, monthly_budget_usd, alert_threshold_pct) VALUES
    ('anthropic',    NULL,              500.00, 80),
    ('bland_ai',     NULL,              300.00, 80),
    ('twilio',       NULL,              100.00, 80),
    ('openrouter',   NULL,               50.00, 80),
    ('google_maps',  NULL,               25.00, 80),
    ('checkr',       NULL,              200.00, 80),
    (NULL,           'ai_llm',          600.00, 80),
    (NULL,           'communications',  450.00, 80),
    (NULL,           'infrastructure',  400.00, 85)
ON CONFLICT DO NOTHING;

-- ── cost_reports ──────────────────────────────────────────────────────────────
-- Archive of generated reports sent to Mark Odom and IEBC team.

CREATE TABLE IF NOT EXISTS cost_reports (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_period     TEXT        NOT NULL,    -- 'YYYY-MM' or 'YYYY-MM (Week of Mon DD)'
    report_type       TEXT        NOT NULL DEFAULT 'weekly',  -- 'weekly' | 'monthly' | 'manual'
    total_cost_usd    NUMERIC(12, 2) NOT NULL,
    breakdown         JSONB       NOT NULL DEFAULT '{}',
    budget_status     JSONB                DEFAULT '{}',
    alerts            JSONB                DEFAULT '[]',
    sent_to           TEXT[],
    sent_at           TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cost_reports_period ON cost_reports (report_period DESC);

-- ── RLS ───────────────────────────────────────────────────────────────────────
ALTER TABLE cost_entries       ENABLE ROW LEVEL SECURITY;
ALTER TABLE cost_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE cost_budgets       ENABLE ROW LEVEL SECURITY;
ALTER TABLE cost_reports       ENABLE ROW LEVEL SECURITY;

-- Service role bypasses RLS; anon/public cannot read cost data
CREATE POLICY "service_role_cost_entries"       ON cost_entries       USING (auth.role() = 'service_role');
CREATE POLICY "service_role_cost_subscriptions" ON cost_subscriptions USING (auth.role() = 'service_role');
CREATE POLICY "service_role_cost_budgets"       ON cost_budgets       USING (auth.role() = 'service_role');
CREATE POLICY "service_role_cost_reports"       ON cost_reports       USING (auth.role() = 'service_role');

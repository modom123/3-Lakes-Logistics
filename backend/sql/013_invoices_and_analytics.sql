-- 013_invoices_and_analytics.sql
-- Invoice table, carrier_stats materialized view, weekly_revenue view

-- ── Invoices ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS invoices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number  TEXT NOT NULL UNIQUE,
    carrier_id      UUID REFERENCES active_carriers(id) ON DELETE SET NULL,
    load_id         UUID REFERENCES loads(id) ON DELETE SET NULL,

    invoice_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date        DATE,
    payment_terms   TEXT DEFAULT 'quick_pay_30',

    amount          NUMERIC(12,2) NOT NULL DEFAULT 0,
    dispatch_fee    NUMERIC(12,2) DEFAULT 0,
    amount_paid     NUMERIC(12,2),

    status          TEXT NOT NULL DEFAULT 'Unpaid'
                        CHECK (status IN ('Unpaid','Paid','Overdue','Void')),

    description     TEXT,
    notes           TEXT,

    payment_ref     TEXT,
    paid_at         TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_invoices_carrier    ON invoices(carrier_id);
CREATE INDEX IF NOT EXISTS idx_invoices_load       ON invoices(load_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status     ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_due_date   ON invoices(due_date);
CREATE INDEX IF NOT EXISTS idx_invoices_date       ON invoices(invoice_date);

-- auto-update updated_at
CREATE OR REPLACE TRIGGER trg_invoices_updated_at
    BEFORE UPDATE ON invoices
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- RLS
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;

CREATE POLICY invoices_service_all ON invoices
    USING (auth.role() = 'service_role');

CREATE POLICY invoices_authenticated_read ON invoices
    FOR SELECT USING (auth.role() = 'authenticated');


-- ── Carrier Stats View ────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW carrier_stats AS
SELECT
    c.id                                                    AS carrier_id,
    c.carrier_name,
    c.mc_number,
    c.dot_number,
    COUNT(DISTINCT l.id)                                    AS total_loads,
    COUNT(DISTINCT l.id) FILTER (WHERE l.status IN ('delivered','closed'))
                                                            AS loads_delivered,
    COALESCE(SUM(l.rate_total) FILTER (WHERE l.status IN ('delivered','closed')), 0)
                                                            AS total_revenue,
    COALESCE(SUM(l.miles) FILTER (WHERE l.status IN ('delivered','closed')), 0)
                                                            AS total_miles,
    COUNT(DISTINCT inv.id)                                  AS invoice_count,
    COALESCE(SUM(inv.amount) FILTER (WHERE inv.status = 'Paid'), 0)
                                                            AS total_collected,
    COALESCE(SUM(inv.amount) FILTER (WHERE inv.status IN ('Unpaid','Overdue')), 0)
                                                            AS total_outstanding,
    MAX(l.delivery_at)                                      AS last_delivery_at
FROM active_carriers c
LEFT JOIN loads       l   ON l.carrier_id = c.id
LEFT JOIN invoices    inv ON inv.carrier_id = c.id
GROUP BY c.id, c.carrier_name, c.mc_number, c.dot_number;


-- ── Weekly Revenue View ───────────────────────────────────────────────────────

CREATE OR REPLACE VIEW weekly_revenue AS
SELECT
    DATE_TRUNC('week', l.delivery_at)::DATE     AS week_start,
    COUNT(*)                                     AS loads_delivered,
    COALESCE(SUM(l.rate_total), 0)               AS gross_revenue,
    COALESCE(SUM(inv.dispatch_fee), 0)           AS dispatch_fees,
    COALESCE(SUM(inv.amount) FILTER (WHERE inv.status = 'Paid'), 0)
                                                 AS collected,
    COALESCE(SUM(inv.amount) FILTER (WHERE inv.status IN ('Unpaid','Overdue')), 0)
                                                 AS outstanding
FROM loads l
LEFT JOIN invoices inv ON inv.load_id = l.id
WHERE l.status IN ('delivered', 'closed')
  AND l.delivery_at IS NOT NULL
GROUP BY DATE_TRUNC('week', l.delivery_at)
ORDER BY week_start DESC;


-- ── Monthly Revenue View ──────────────────────────────────────────────────────

CREATE OR REPLACE VIEW monthly_revenue AS
SELECT
    DATE_TRUNC('month', l.delivery_at)::DATE     AS month_start,
    TO_CHAR(l.delivery_at, 'YYYY-MM')            AS period,
    COUNT(*)                                     AS loads_delivered,
    COUNT(DISTINCT l.carrier_id)                 AS active_carriers,
    COALESCE(SUM(l.rate_total), 0)               AS gross_revenue,
    COALESCE(SUM(inv.dispatch_fee), 0)           AS dispatch_fees,
    COALESCE(SUM(l.miles), 0)                    AS total_miles,
    CASE WHEN SUM(l.miles) > 0
         THEN ROUND(SUM(l.rate_total) / SUM(l.miles), 3)
         ELSE 0
    END                                          AS avg_rpm,
    COALESCE(SUM(inv.amount) FILTER (WHERE inv.status = 'Paid'), 0)
                                                 AS collected,
    COALESCE(SUM(inv.amount) FILTER (WHERE inv.status IN ('Unpaid','Overdue')), 0)
                                                 AS outstanding
FROM loads l
LEFT JOIN invoices inv ON inv.load_id = l.id
WHERE l.status IN ('delivered', 'closed')
  AND l.delivery_at IS NOT NULL
GROUP BY DATE_TRUNC('month', l.delivery_at), TO_CHAR(l.delivery_at, 'YYYY-MM')
ORDER BY month_start DESC;


-- ── Driver Stats View ─────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW driver_performance AS
SELECT
    l.driver_id,
    l.driver_name,
    l.carrier_id,
    COUNT(*)                                        AS loads_delivered,
    COALESCE(SUM(l.miles), 0)                       AS total_miles,
    COALESCE(SUM(l.rate_total), 0)                  AS gross_rate_total,
    ROUND(COALESCE(SUM(l.rate_total), 0) * 0.72, 2) AS driver_gross_pay,
    CASE WHEN SUM(l.miles) > 0
         THEN ROUND(SUM(l.rate_total) / SUM(l.miles), 3)
         ELSE 0
    END                                             AS avg_rpm,
    MAX(l.delivery_at)                              AS last_delivery_at
FROM loads l
WHERE l.status IN ('delivered', 'closed')
  AND l.driver_id IS NOT NULL
GROUP BY l.driver_id, l.driver_name, l.carrier_id;


-- ── Load Funnel View ──────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW load_funnel AS
SELECT
    status,
    COUNT(*)                                AS load_count,
    COALESCE(SUM(rate_total), 0)            AS total_value,
    ROUND(AVG(rate_total)::NUMERIC, 2)      AS avg_value
FROM loads
GROUP BY status;

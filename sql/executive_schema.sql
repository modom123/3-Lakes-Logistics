-- ============================================================
-- IEBC Executive Command Schema
-- 18 executives (5 cabinet + 13 expansion), KPI engine,
-- triage system, daily briefs, contingency plans
-- ============================================================

-- executives table
CREATE TABLE IF NOT EXISTS executives (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    title text NOT NULL,
    department text NOT NULL,  -- 'operations','finance','growth','technical','carrier_experience','security','process'
    reports_to text DEFAULT 'commander',  -- 'commander' or another exec id/name
    manages text[],  -- list of agent names or dept workers they manage
    primary_kpi text,
    kpi_target text,
    kpi_definition text,
    contingency_owned text,  -- which contingency plan they own
    status text DEFAULT 'active',
    avatar_initials text,  -- e.g. 'ES' for Evelyn Sterling
    avatar_color text,  -- hex color for avatar
    hired_at timestamptz DEFAULT now(),
    created_at timestamptz DEFAULT now()
);

-- kpi_snapshots — daily KPI readings per executive
CREATE TABLE IF NOT EXISTS executive_kpi_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    executive_id uuid REFERENCES executives(id),
    kpi_name text NOT NULL,
    target_value numeric,
    current_value numeric,
    unit text,  -- 'percent', 'dollars', 'hours', 'ms', 'score'
    status text DEFAULT 'on_track',  -- 'on_track','at_risk','critical'
    notes text,
    snapshot_date date DEFAULT CURRENT_DATE,
    created_at timestamptz DEFAULT now()
);

-- triage_escalations — 3-tier triage system
CREATE TABLE IF NOT EXISTS triage_escalations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tier int NOT NULL CHECK (tier IN (1,2,3)),
    event_type text NOT NULL,  -- 'ocr_failure','safety_red','api_down','fraud_alert','dispute','gps_lag','rate_variance'
    description text,
    load_id uuid,
    driver_id uuid,
    assigned_to text,  -- executive name or 'ai_agent' or 'commander'
    status text DEFAULT 'open',  -- 'open','in_review','resolved','escalated'
    auto_resolved boolean DEFAULT false,
    resolution_notes text,
    escalated_from_tier int,
    created_at timestamptz DEFAULT now(),
    resolved_at timestamptz
);

-- daily_briefs — State of the Fleet report from Dr. Evelyn Sterling
CREATE TABLE IF NOT EXISTS daily_briefs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    date date DEFAULT CURRENT_DATE,
    authored_by text DEFAULT 'Dr. Evelyn Sterling',
    tier1_resolved int DEFAULT 0,
    tier2_resolved int DEFAULT 0,
    tier3_items jsonb DEFAULT '[]',
    fleet_uptime_pct numeric DEFAULT 99.99,
    active_loads int DEFAULT 0,
    revenue_today numeric DEFAULT 0,
    alerts jsonb DEFAULT '[]',
    master_scores jsonb DEFAULT '{}',
    summary text,
    created_at timestamptz DEFAULT now()
);

-- contingency_plans registry
CREATE TABLE IF NOT EXISTS contingency_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    problem text,
    solution text,
    iebc_lead text,
    trigger_condition text,
    automation_step int,  -- which of the 200 steps this maps to
    status text DEFAULT 'active',
    last_triggered_at timestamptz,
    trigger_count int DEFAULT 0,
    created_at timestamptz DEFAULT now()
);

-- indexes
CREATE INDEX IF NOT EXISTS idx_escalations_status ON triage_escalations(status);
CREATE INDEX IF NOT EXISTS idx_escalations_tier ON triage_escalations(tier);
CREATE INDEX IF NOT EXISTS idx_kpi_snapshots_exec ON executive_kpi_snapshots(executive_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_briefs_date ON daily_briefs(date);

-- RLS
ALTER TABLE executives ENABLE ROW LEVEL SECURITY;
ALTER TABLE triage_escalations ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_briefs ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- SEED DATA — 18 Executives
-- ============================================================

-- Cabinet (5)
INSERT INTO executives (name, title, department, reports_to, manages, primary_kpi, kpi_target, kpi_definition, contingency_owned, avatar_initials, avatar_color)
VALUES
(
    'Dr. Evelyn Sterling',
    'COO',
    'operations',
    'commander',
    ARRAY['Scout','Shield','Penny','Marcus Reid','all_agents'],
    '200-Step Uptime',
    '99.99%',
    'Percentage of time all 200 automation steps execute without failure across the fleet',
    'Triage Escalation Hierarchy',
    'ES',
    '#1B3E75'
),
(
    'Eleanor Wei',
    'CFO',
    'finance',
    'commander',
    ARRAY['Aisha Kapoor','David Chen','Dr. Charles Montgomery'],
    'EBITDA Margin',
    'Zero financial leakage',
    'Earnings before interest, taxes, depreciation, and amortization as a percentage of revenue with zero unexplained variance',
    'Financial Variance Thresholds',
    'EW',
    '#2D6A4F'
),
(
    'Arthur Vance',
    'VP Global Operations',
    'operations',
    'commander',
    ARRAY['Winston Carmichael','Dr. Anika Patel','1000-unit fleet'],
    'Fleet Resource Allocation',
    '100% utilization',
    'Percentage of fleet trucks actively dispatched or staged — zero idle assets',
    'Dynamic Geo-Fencing & Delta Tracking',
    'AV',
    '#6B2D8B'
),
(
    'Katerina Rostova',
    'Head of Process Automation',
    'process',
    'commander',
    ARRAY['DAG logic','200-step mapping'],
    'OCR Confidence Score',
    '>95%',
    'Average confidence score of OCR document reads across all ingested BOLs, rate cons, and lumper receipts',
    'OCR Verification & AI-Refinement Loop',
    'KR',
    '#C65D00'
),
(
    'Casey Monroe',
    'Security Lead',
    'security',
    'commander',
    ARRAY['RLS auditing','atomic ledger'],
    'Security Audit Score',
    'Zero breaches',
    'Composite score of RLS policy coverage, failed auth attempts blocked, and ledger integrity checks passing',
    NULL,
    'CM',
    '#7B1D1D'
);

-- Expansion Group 1 — Growth (report to commander / growth dept)
INSERT INTO executives (name, title, department, reports_to, manages, primary_kpi, kpi_target, avatar_initials, avatar_color)
VALUES
(
    'Sterling Pierce',
    'Chief Revenue Officer',
    'growth',
    'commander',
    ARRAY['lead pipeline','broker outreach','shipper development'],
    'Growth Velocity',
    'MoM revenue growth > 15%',
    'SP',
    '#1A6B3C'
),
(
    'Benjamin Mercer',
    'Director of Market Positioning',
    'growth',
    'Sterling Pierce',
    ARRAY['brand strategy','competitive intel'],
    'Market Share Index',
    'Top 3 regional positioning',
    'BM',
    '#2A5C8A'
),
(
    'Dr. Elena Kincaid',
    'Chief Futurist',
    'growth',
    'Sterling Pierce',
    ARRAY['AI roadmap','predictive modeling','innovation pipeline'],
    'Innovation Pipeline Score',
    '3+ active R&D initiatives',
    'EK',
    '#5B4E8B'
);

-- Expansion Group 2 — Finance (report to Eleanor Wei)
INSERT INTO executives (name, title, department, reports_to, manages, primary_kpi, kpi_target, avatar_initials, avatar_color)
VALUES
(
    'Aisha Kapoor',
    'Director of Financial Forecasting',
    'finance',
    'Eleanor Wei',
    ARRAY['budget models','cash flow projections'],
    'Forecast Accuracy',
    'Variance < 3% from actuals',
    'AK',
    '#1F6B5E'
),
(
    'David Chen',
    'Director of Risk Management',
    'finance',
    'Eleanor Wei',
    ARRAY['insurance review','carrier credit scoring','fraud detection'],
    'Risk Exposure Score',
    'Zero uncovered liabilities',
    'DC',
    '#4A3728'
),
(
    'Dr. Charles Montgomery',
    'Quantitative Analyst',
    'finance',
    'Eleanor Wei',
    ARRAY['rate optimization','lane profitability','RPM modeling'],
    'RPM Optimization Delta',
    'RPM > $2.85 avg',
    'CM',
    '#3D1F6B'
);

-- Expansion Group 3 — Carrier/Driver Experience (report to Arthur Vance)
INSERT INTO executives (name, title, department, reports_to, manages, primary_kpi, kpi_target, avatar_initials, avatar_color)
VALUES
(
    'Winston Carmichael',
    'Director of Carrier Success',
    'carrier_experience',
    'Arthur Vance',
    ARRAY['carrier onboarding','dispatch quality','carrier satisfaction'],
    'Carrier NPS',
    'Score > 75',
    'WC',
    '#1B4E6B'
),
(
    'Dr. Anika Patel',
    'Director of Driver Retention',
    'carrier_experience',
    'Arthur Vance',
    ARRAY['driver wellness','safety score tracking','churn prevention'],
    'Driver Retention Rate',
    '> 90% 90-day retention',
    'AP',
    '#6B3D1B'
),
(
    'Diego Martinez',
    'AI Support Bot Lead',
    'carrier_experience',
    'Arthur Vance',
    ARRAY['chatbot pipeline','driver FAQ','escalation routing'],
    'Bot Resolution Rate',
    '> 80% tier-1 auto-resolved',
    'DM',
    '#1B6B2E'
);

-- Expansion Group 4 — Technical (report to Dr. Evelyn Sterling / COO)
INSERT INTO executives (name, title, department, reports_to, manages, primary_kpi, kpi_target, avatar_initials, avatar_color)
VALUES
(
    'Sam Torres',
    'API Specification Lead',
    'technical',
    'Dr. Evelyn Sterling',
    ARRAY['OpenAPI spec','webhook contracts','integration docs'],
    'API Uptime',
    '99.9% SLA',
    'ST',
    '#2A6B5E'
),
(
    'Amara Cole',
    'Database Architect',
    'technical',
    'Dr. Evelyn Sterling',
    ARRAY['Supabase schema','RLS policies','migration pipeline'],
    'Query P95 Latency',
    '< 80ms',
    'AC',
    '#6B4E1B'
),
(
    'Jamie Park',
    'QA Lead',
    'technical',
    'Dr. Evelyn Sterling',
    ARRAY['test suite','regression pipeline','staging environment'],
    'Test Coverage',
    '> 85% code coverage',
    'JP',
    '#3D6B1B'
),
(
    'Dr. Hiroshi Tanaka',
    'AI Systems Consultant',
    'technical',
    'Dr. Evelyn Sterling',
    ARRAY['LLM fine-tuning','agent orchestration','ML ops'],
    'Model Accuracy Score',
    '> 92% task completion rate',
    'HT',
    '#1B3D6B'
);

-- ============================================================
-- SEED DATA — 5 Contingency Plans
-- ============================================================

INSERT INTO contingency_plans (name, problem, solution, iebc_lead, trigger_condition, automation_step)
VALUES
(
    'OCR Verification & AI-Refinement Loop',
    'OCR confidence score drops below 95% on document ingestion — BOLs, rate cons, or lumper receipts parsed with low accuracy leading to billing errors',
    'Trigger secondary AI refinement pass using GPT-4 Vision with structured extraction prompt. Flag document for human review if second pass still below threshold. Block invoice generation until manual approval.',
    'Katerina Rostova',
    'OCR confidence score < 95% on any document type',
    27
),
(
    'API Resilience & Polling Fallback',
    'Webhook delivery fails or API endpoint returns 5xx — downstream systems miss critical load status updates, payment triggers, or ELD data',
    'Switch to exponential backoff polling (15s, 30s, 60s, 5m intervals). Store events in dead-letter queue. Replay missed webhooks once endpoint recovers. Alert Marcus Reid (CTO) if downtime exceeds 5 minutes.',
    'Marcus Reid',
    'Webhook 5xx error or connection timeout > 10 seconds',
    45
),
(
    'Triage Escalation Hierarchy',
    'Safety red event, critical system failure, or tier-3 escalation requires immediate commander-level decision',
    'Tier 1 (AI auto-resolve within 15 min) → Tier 2 (assigned executive, 1hr SLA) → Tier 3 (Commander + COO war room, immediate). All tier-3 items logged to daily brief. Dr. Evelyn Sterling owns daily brief summary.',
    'Dr. Evelyn Sterling',
    'Safety red flag, tier-2 unresolved after 1hr, or critical system event',
    1
),
(
    'Dynamic Geo-Fencing & Delta Tracking',
    'GPS signal loss, truck deviates from planned route by more than delta threshold, or driver enters restricted geo-fence zone',
    'Auto-trigger geo-fence alert to dispatcher. Compare current coordinates against planned route polyline. If delta > 15 miles, escalate to Arthur Vance. Log deviation in telemetry. Auto-notify broker if ETA shifts > 2 hours.',
    'Arthur Vance',
    'GPS delta > 15 miles from planned route or geo-fence breach detected',
    61
),
(
    'Financial Variance Thresholds',
    'Invoice amount, rate-per-mile, or EBITDA margin deviates beyond acceptable variance bands — potential fraud, billing error, or system miscalculation',
    'Flag transaction for Eleanor Wei review. Auto-freeze payment processing for flagged invoice. Cross-reference against load rate con and broker credit score. Escalate to David Chen (Risk) if variance exceeds $500 or RPM delta > 15%. Log to atomic ledger.',
    'Eleanor Wei',
    'Invoice variance > 5% from rate con, RPM delta > 15%, or EBITDA dip > 2pts in single day',
    112
);

-- ============================================================
-- Migration 029 — Executive Suite Update
-- 1. Victoria Roth: Chief Strategy Officer → Chief Growth Officer
-- 2. Add Mark Odom — CEO & Commander (top of org chart)
-- 3. Add CC Gulley — Chief Strategy Officer
-- ============================================================

-- 1. Victoria Roth → Chief Growth Officer
UPDATE executives
SET
    title = 'Chief Growth Officer',
    kpi_definition = 'Composite score of MoM revenue growth, carrier acquisition velocity, lead pipeline conversion, and market share expansion. Owns the full growth engine.',
    kpi_target = '>87 / MoM revenue growth > 15%'
WHERE name = 'Victoria Roth';

-- 2. Mark Odom — CEO & Commander
INSERT INTO executives (
    name, title, department, reports_to, manages,
    primary_kpi, kpi_target, kpi_definition,
    contingency_owned, avatar_initials, avatar_color
) VALUES (
    'Mark Odom',
    'CEO — Commander',
    'executive',
    NULL,
    ARRAY[
        'Dr. Evelyn Sterling', 'Eleanor Wei', 'Arthur Vance',
        'Katerina Rostova', 'Casey Monroe', 'CC Gulley',
        'Victoria Roth', 'Sterling Pierce', 'all_executives'
    ],
    'Company Growth Velocity',
    '$300K ARR / 1,000 Founders trucks',
    'Top-line revenue growth toward $300K ARR (1,000 trucks × $300/mo). Monitors master scores daily, owns all Tier-3 escalations, and issues Commander directives to the full executive team.',
    'Triage Escalation Hierarchy',
    'MO',
    '#0B1F4B'
);

-- 3. CC Gulley — Chief Strategy Officer
INSERT INTO executives (
    name, title, department, reports_to, manages,
    primary_kpi, kpi_target, kpi_definition,
    avatar_initials, avatar_color
) VALUES (
    'CC Gulley',
    'Chief Strategy Officer',
    'strategy',
    'commander',
    ARRAY[
        'Alexander Wright', 'Benjamin Mercer',
        'market_positioning', 'competitive_intel',
        'partnership_strategy', '30_60_90_roadmap'
    ],
    'Strategic Execution Score',
    '90%+ initiative on-track rate',
    'Percentage of active strategic initiatives hitting milestone targets across the 30/60/90-day roadmap. Measures how well strategy translates to execution across all departments.',
    'CC',
    '#1A5C8A'
);

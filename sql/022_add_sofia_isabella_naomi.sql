-- ============================================================
-- Migration 022 — Add Sofia Rossi, Isabella Cruz, Naomi Kensington
-- Finance Automation + Outreach executives (IEBC Workforce Expansion)
-- Note: Katerina Rostova & Winston Carmichael already seeded in
--       executive_schema.sql — only agent wiring added this session.
-- Total executives: 20 → 23
-- ============================================================

-- Sofia Rossi — Dir. Financial Automation (reports to Eleanor Wei)
INSERT INTO executives (
    name, title, department, reports_to, manages,
    primary_kpi, kpi_target, kpi_definition,
    avatar_initials, avatar_color
) VALUES (
    'Sofia Rossi',
    'Director of Financial Automation',
    'finance',
    'Eleanor Wei',
    ARRAY['invoice pipeline', 'AR reconciliation', 'Stripe-Plaid sync'],
    'AR Collection Rate',
    '> 95% collected within 30 days',
    'Percentage of issued invoices collected within 30 days. Zero unexplained variance between rate con and invoice amount. Missing invoice count must be 0.',
    'SR',
    '#2D5A3D'
);

-- Isabella Cruz — VP Omnichannel Outreach (reports to Sterling Pierce)
INSERT INTO executives (
    name, title, department, reports_to, manages,
    primary_kpi, kpi_target, kpi_definition,
    avatar_initials, avatar_color
) VALUES (
    'Isabella Cruz',
    'VP Omnichannel Outreach',
    'growth',
    'Sterling Pierce',
    ARRAY['outreach campaigns', 'lead nurture sequences', 'Vance call scripts'],
    'Campaign Conversion Rate',
    '> 12% lead-to-call booked',
    'Percentage of outreach campaign contacts that result in a booked discovery call within 7 days. Feeds directly into Vance dial list and Isabella campaign engine.',
    'IC',
    '#8B3A6B'
);

-- Naomi Kensington — Head Predictive Targeting (reports to Isabella Cruz)
INSERT INTO executives (
    name, title, department, reports_to, manages,
    primary_kpi, kpi_target, kpi_definition,
    avatar_initials, avatar_color
) VALUES (
    'Naomi Kensington',
    'Head of Predictive Targeting',
    'growth',
    'Isabella Cruz',
    ARRAY['lead scoring model', 'ML targeting', 'Tier A/B/C segmentation'],
    'Predictive Score Accuracy',
    '> 85% of Tier A leads convert to call',
    'Percentage of leads scored Tier A (predictive_score >= 10) that result in a live carrier call within 14 days. Validates the scoring model against real conversion outcomes.',
    'NK',
    '#4A2D8B'
);

-- ============================================================
-- Migration 021 — Add Victoria Roth & Alexander Wright
-- Strategy & Growth executives (IEBC Employees 1 & 2)
-- Total executives: 18 → 20
-- ============================================================

-- Victoria Roth — Chief Growth Officer (Cabinet level)
-- Note: Title updated from Chief Strategy Officer → Chief Growth Officer in migration 029
INSERT INTO executives (
    name, title, department, reports_to, manages,
    primary_kpi, kpi_target, kpi_definition,
    avatar_initials, avatar_color
) VALUES (
    'Victoria Roth',
    'Chief Growth Officer',
    'growth',
    'commander',
    ARRAY['Alexander Wright', 'Benjamin Mercer', 'Sterling Pierce', 'growth_division'],
    'Growth Velocity Score',
    '>87 / MoM revenue growth > 15%',
    'Composite score of MoM revenue growth, carrier acquisition velocity, lead pipeline conversion, and market share expansion. Owns the full growth engine.',
    'VR',
    '#8B1A1A'
);

-- Alexander Wright — VP Market Intelligence (reports to Victoria Roth)
INSERT INTO executives (
    name, title, department, reports_to, manages,
    primary_kpi, kpi_target, kpi_definition,
    avatar_initials, avatar_color
) VALUES (
    'Alexander Wright',
    'VP Market Intelligence',
    'growth',
    'Victoria Roth',
    ARRAY['DOT data pipeline', 'FMCSA competitor analysis', 'lane opportunity models'],
    'Market Signal Accuracy',
    '>90% predictive accuracy on lane demand',
    'Percentage accuracy of DOT/FMCSA-derived lane demand predictions vs. actual load board availability. Feeds directly into Sonny load-board targeting and Sterling Pierce growth strategy.',
    'AW',
    '#1A4A8B'
);

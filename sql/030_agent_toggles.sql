-- Agent on/off toggles
-- Stores the enabled state for each agent.
-- Missing rows default to enabled (true) at the application layer.

CREATE TABLE IF NOT EXISTS agent_toggles (
    agent_name   TEXT PRIMARY KEY,
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by   TEXT NOT NULL DEFAULT 'system'
);

-- Seed all known agents as enabled
INSERT INTO agent_toggles (agent_name) VALUES
    ('alexander'),
    ('atlas'),
    ('audit'),
    ('beacon'),
    ('bond_courier'),
    ('chloe_sinclair'),
    ('echo'),
    ('isabella'),
    ('james_bond'),
    ('katerina'),
    ('lucas_sterling'),
    ('naomi'),
    ('nova'),
    ('orbit'),
    ('outside_bond'),
    ('penny'),
    ('pulse'),
    ('scout'),
    ('settler'),
    ('shield'),
    ('signal'),
    ('sofia'),
    ('sonny'),
    ('technical_team'),
    ('vance'),
    ('victoria'),
    ('winston')
ON CONFLICT (agent_name) DO NOTHING;

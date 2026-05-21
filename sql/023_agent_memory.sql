-- ============================================================
-- Migration 023 — Org Brain: Agent Memory & Interaction Tables
-- Gives every AI agent persistent memory and cross-agent learning
-- ============================================================

-- agent_memory: what each agent has learned and remembered
CREATE TABLE IF NOT EXISTS agent_memory (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name      text NOT NULL,          -- 'naomi', 'alexander', 'org' (shared)
    memory_key      text NOT NULL,          -- 'hot_states', 'score_weights', 'churn_signals'
    memory_value    jsonb NOT NULL,         -- the learned data
    confidence      float DEFAULT 0.5      -- 0.0–1.0, grows with reinforcement
        CHECK (confidence >= 0 AND confidence <= 1),
    source_agent    text,                   -- who originally generated this insight
    interaction_count int DEFAULT 1,        -- reinforcement counter
    summary         text,                   -- human-readable 1-liner of what was learned
    created_at      timestamptz DEFAULT now(),
    updated_at      timestamptz DEFAULT now(),
    UNIQUE(agent_name, memory_key)          -- one living memory per key per agent
);

-- agent_interactions: log of every cross-agent knowledge exchange
CREATE TABLE IF NOT EXISTS agent_interactions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_agent      text NOT NULL,
    to_agent        text NOT NULL,
    interaction_type text NOT NULL          -- 'handoff', 'query', 'feedback', 'broadcast', 'directive'
        CHECK (interaction_type IN ('handoff','query','feedback','broadcast','directive')),
    payload         jsonb DEFAULT '{}',     -- what was sent
    result          jsonb DEFAULT '{}',     -- what came back
    outcome         text DEFAULT 'pending' -- 'success', 'partial', 'failed', 'pending'
        CHECK (outcome IN ('success','partial','failed','pending')),
    outcome_notes   text,
    created_at      timestamptz DEFAULT now()
);

-- indexes
CREATE INDEX IF NOT EXISTS idx_agent_memory_name    ON agent_memory(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_memory_key     ON agent_memory(agent_name, memory_key);
CREATE INDEX IF NOT EXISTS idx_agent_memory_source  ON agent_memory(source_agent);
CREATE INDEX IF NOT EXISTS idx_interactions_from    ON agent_interactions(from_agent, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_interactions_to      ON agent_interactions(to_agent, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_interactions_created ON agent_interactions(created_at DESC);

-- RLS
ALTER TABLE agent_memory        ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_interactions  ENABLE ROW LEVEL SECURITY;

-- ── Seed: initial org-level shared memories ──────────────────────────────────
-- These act as default context before the first real run

INSERT INTO agent_memory (agent_name, memory_key, memory_value, confidence, source_agent, summary)
VALUES
(
    'org',
    'strategic_directive',
    '{"priority": "carrier_acquisition", "focus_regions": [], "target_fleet_size": "2-10", "note": "Initial directive — updated by Victoria after first strategic snapshot"}',
    0.3,
    'victoria',
    'Initial strategic directive — Victoria will update after first run'
),
(
    'org',
    'scoring_baseline',
    '{"high_value_equipment": ["dry van","reefer","flatbed","step deck","power only"], "min_fleet_for_tier_a": 5, "inactivity_threshold_days": 14}',
    0.6,
    'naomi',
    'Baseline scoring parameters — Naomi refines from Vance call outcomes'
);

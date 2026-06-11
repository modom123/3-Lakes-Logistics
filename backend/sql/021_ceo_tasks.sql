-- Migration 021 — CEO task list (Mark Odom → CC Gulley) server persistence.
--
-- Backs the "Todo → CC Gulley" tab in the executive offices so tasks survive
-- across browsers/devices instead of living only in localStorage.

CREATE TABLE IF NOT EXISTS ceo_tasks (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner        TEXT NOT NULL DEFAULT 'mark',        -- office that created the task
    assigned_to  TEXT NOT NULL DEFAULT 'cc_gulley',   -- agent the task is routed to
    title        TEXT NOT NULL,
    description  TEXT,
    due_date     DATE,
    priority     TEXT NOT NULL DEFAULT 'med',         -- high | med | low
    category     TEXT NOT NULL DEFAULT 'strategy',
    done         BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ceo_tasks_owner ON ceo_tasks (owner);
CREATE INDEX IF NOT EXISTS idx_ceo_tasks_open  ON ceo_tasks (owner, done);

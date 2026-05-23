-- Bond Channel: bidirectional message table between IEBC Internal
-- James Bond and External James Bond on Daytona.
--
-- Run once in Supabase SQL editor.
-- RLS disabled intentionally — access controlled at API layer.

CREATE TABLE IF NOT EXISTS bond_channel (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    direction     TEXT NOT NULL
                    CHECK (direction IN ('internal_to_external', 'external_to_internal')),
    from_label    TEXT NOT NULL,
    message_type  TEXT NOT NULL DEFAULT 'directive'
                    CHECK (message_type IN ('directive','report','feedback','suggestion','acknowledgment')),
    content       TEXT NOT NULL,
    priority      TEXT NOT NULL DEFAULT 'normal'
                    CHECK (priority IN ('critical','high','normal','low')),
    status        TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','delivered','read','actioned')),
    metadata      JSONB DEFAULT '{}',
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS bond_channel_direction_status
    ON bond_channel (direction, status, created_at);

CREATE OR REPLACE FUNCTION bond_channel_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS bond_channel_updated_at ON bond_channel;
CREATE TRIGGER bond_channel_updated_at
    BEFORE UPDATE ON bond_channel
    FOR EACH ROW EXECUTE FUNCTION bond_channel_set_updated_at();

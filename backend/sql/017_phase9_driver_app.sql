-- Phase 9: Driver Mobile App Schema
-- Tables driver_messages, driver_sessions, driver_payouts were created earlier.
-- This migration adds missing columns, indexes, RLS policies, and triggers.

-- ── 1. Missing columns on drivers ────────────────────────────────────────────
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS app_version text;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS last_location jsonb;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS last_location_at timestamptz;

-- ── 2. Missing column on driver_messages ─────────────────────────────────────
ALTER TABLE driver_messages ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

-- ── 3. Indexes ────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_driver_messages_phone_created  ON driver_messages(driver_phone, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_driver_messages_driver_id       ON driver_messages(driver_id);
CREATE INDEX IF NOT EXISTS idx_driver_messages_load_id         ON driver_messages(load_id);
CREATE INDEX IF NOT EXISTS idx_driver_sessions_token           ON driver_sessions(token);
CREATE INDEX IF NOT EXISTS idx_driver_sessions_driver_id       ON driver_sessions(driver_id);
CREATE INDEX IF NOT EXISTS idx_driver_sessions_expires_at      ON driver_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_driver_payouts_driver_id        ON driver_payouts(driver_id);
CREATE INDEX IF NOT EXISTS idx_driver_payouts_status           ON driver_payouts(status);
CREATE INDEX IF NOT EXISTS idx_driver_payouts_load_id          ON driver_payouts(load_id);
CREATE INDEX IF NOT EXISTS idx_loads_driver_id                 ON loads(driver_id);
CREATE INDEX IF NOT EXISTS idx_loads_status_pickup_at          ON loads(status, pickup_at DESC);
CREATE INDEX IF NOT EXISTS idx_drivers_phone_e164              ON drivers(phone_e164);
CREATE INDEX IF NOT EXISTS idx_loads_delivered_at              ON loads(delivered_at DESC);

-- ── 4. RLS — driver_sessions ──────────────────────────────────────────────────
DROP POLICY IF EXISTS driver_sessions_driver_access ON driver_sessions;
DROP POLICY IF EXISTS driver_sessions_select ON driver_sessions;
DROP POLICY IF EXISTS driver_sessions_insert ON driver_sessions;
DROP POLICY IF EXISTS driver_sessions_delete ON driver_sessions;
CREATE POLICY driver_sessions_select ON driver_sessions
  FOR SELECT USING (driver_id::text = current_setting('app.current_driver_id', true));
CREATE POLICY driver_sessions_insert ON driver_sessions
  FOR INSERT WITH CHECK (driver_id::text = current_setting('app.current_driver_id', true));
CREATE POLICY driver_sessions_delete ON driver_sessions
  FOR DELETE USING (driver_id::text = current_setting('app.current_driver_id', true));

-- ── 5. RLS — driver_messages ─────────────────────────────────────────────────
DROP POLICY IF EXISTS driver_messages_driver_access ON driver_messages;
DROP POLICY IF EXISTS driver_messages_select ON driver_messages;
DROP POLICY IF EXISTS driver_messages_insert ON driver_messages;
DROP POLICY IF EXISTS driver_messages_update ON driver_messages;
CREATE POLICY driver_messages_select ON driver_messages
  FOR SELECT USING (driver_id::text = current_setting('app.current_driver_id', true));
CREATE POLICY driver_messages_insert ON driver_messages
  FOR INSERT WITH CHECK (direction = 'outbound');
CREATE POLICY driver_messages_update ON driver_messages
  FOR UPDATE USING (driver_id::text = current_setting('app.current_driver_id', true))
  WITH CHECK (driver_id::text = current_setting('app.current_driver_id', true));

-- ── 6. RLS — driver_payouts ──────────────────────────────────────────────────
DROP POLICY IF EXISTS driver_payouts_driver_access ON driver_payouts;
DROP POLICY IF EXISTS driver_payouts_select ON driver_payouts;
CREATE POLICY driver_payouts_select ON driver_payouts
  FOR SELECT USING (driver_id::text = current_setting('app.current_driver_id', true));

-- ── 7. Grants ─────────────────────────────────────────────────────────────────
GRANT ALL ON driver_sessions TO service_role;
GRANT ALL ON driver_messages TO service_role;
GRANT ALL ON driver_payouts  TO service_role;
GRANT SELECT, INSERT, UPDATE ON driver_messages TO anon;
GRANT SELECT ON driver_payouts TO anon;
GRANT SELECT ON driver_sessions TO anon;

-- ── 8. Session cleanup utility ────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS void LANGUAGE sql SECURITY DEFINER AS $$
  DELETE FROM driver_sessions WHERE expires_at < now();
$$;

-- ── 9. updated_at triggers ────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS driver_messages_updated_at ON driver_messages;
CREATE TRIGGER driver_messages_updated_at
  BEFORE UPDATE ON driver_messages
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS driver_payouts_updated_at ON driver_payouts;
CREATE TRIGGER driver_payouts_updated_at
  BEFORE UPDATE ON driver_payouts
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

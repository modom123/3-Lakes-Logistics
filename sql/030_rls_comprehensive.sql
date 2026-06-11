-- ============================================================
-- 3 Lakes Logistics — Comprehensive Row Level Security
-- Ensures all sensitive tables have RLS enforced.
-- Run AFTER driver_schema_additions.sql and grant_access_and_rls.sql
-- ============================================================

-- ── Enable RLS on all sensitive tables ──────────────────────

ALTER TABLE public.drivers          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loads            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.driver_sessions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.driver_messages  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.driver_payouts   ENABLE ROW LEVEL SECURITY;

-- ── Drop all policies before recreating (safe re-run) ───────

DROP POLICY IF EXISTS driver_sessions_driver_access    ON public.driver_sessions;
DROP POLICY IF EXISTS driver_messages_driver_access    ON public.driver_messages;
DROP POLICY IF EXISTS driver_payouts_driver_access     ON public.driver_payouts;

DROP POLICY IF EXISTS "drivers_select_own"             ON public.drivers;
DROP POLICY IF EXISTS "drivers_update_own"             ON public.drivers;
DROP POLICY IF EXISTS "drivers_service_role"           ON public.drivers;

DROP POLICY IF EXISTS "loads_select_driver"            ON public.loads;
DROP POLICY IF EXISTS "loads_update_own"               ON public.loads;
DROP POLICY IF EXISTS "loads_service_role"             ON public.loads;

DROP POLICY IF EXISTS "driver_sessions_select_own"     ON public.driver_sessions;
DROP POLICY IF EXISTS "driver_sessions_delete_own"     ON public.driver_sessions;
DROP POLICY IF EXISTS "driver_sessions_service_role"   ON public.driver_sessions;

DROP POLICY IF EXISTS "driver_messages_select_own"     ON public.driver_messages;
DROP POLICY IF EXISTS "driver_messages_insert_own"     ON public.driver_messages;
DROP POLICY IF EXISTS "driver_messages_update_own"     ON public.driver_messages;
DROP POLICY IF EXISTS "driver_messages_service_role"   ON public.driver_messages;

DROP POLICY IF EXISTS "driver_payouts_select_own"      ON public.driver_payouts;
DROP POLICY IF EXISTS "driver_payouts_service_role"    ON public.driver_payouts;

-- ── DRIVERS table ────────────────────────────────────────────

CREATE POLICY "drivers_select_own"
  ON public.drivers FOR SELECT TO authenticated
  USING (id = (SELECT id FROM drivers WHERE auth_user_id = auth.uid() LIMIT 1));

CREATE POLICY "drivers_update_own"
  ON public.drivers FOR UPDATE TO authenticated
  USING (id = (SELECT id FROM drivers WHERE auth_user_id = auth.uid() LIMIT 1))
  WITH CHECK (id = (SELECT id FROM drivers WHERE auth_user_id = auth.uid() LIMIT 1));

CREATE POLICY "drivers_service_role"
  ON public.drivers TO service_role USING (true);

-- ── LOADS table ──────────────────────────────────────────────

CREATE POLICY "loads_select_driver"
  ON public.loads FOR SELECT TO authenticated
  USING (
    status = 'booked'
    OR driver_id = (SELECT id FROM drivers WHERE auth_user_id = auth.uid() LIMIT 1)
  );

CREATE POLICY "loads_update_own"
  ON public.loads FOR UPDATE TO authenticated
  USING (driver_id = (SELECT id FROM drivers WHERE auth_user_id = auth.uid() LIMIT 1))
  WITH CHECK (driver_id = (SELECT id FROM drivers WHERE auth_user_id = auth.uid() LIMIT 1));

CREATE POLICY "loads_service_role"
  ON public.loads TO service_role USING (true);

-- ── DRIVER SESSIONS table ────────────────────────────────────

CREATE POLICY "driver_sessions_select_own"
  ON public.driver_sessions FOR SELECT TO authenticated
  USING (driver_id = (SELECT id FROM drivers WHERE auth_user_id = auth.uid() LIMIT 1));

CREATE POLICY "driver_sessions_delete_own"
  ON public.driver_sessions FOR DELETE TO authenticated
  USING (driver_id = (SELECT id FROM drivers WHERE auth_user_id = auth.uid() LIMIT 1));

CREATE POLICY "driver_sessions_service_role"
  ON public.driver_sessions TO service_role USING (true);

-- ── DRIVER MESSAGES table ────────────────────────────────────

CREATE POLICY "driver_messages_select_own"
  ON public.driver_messages FOR SELECT TO authenticated
  USING (driver_id = (SELECT id FROM drivers WHERE auth_user_id = auth.uid() LIMIT 1));

CREATE POLICY "driver_messages_insert_own"
  ON public.driver_messages FOR INSERT TO authenticated
  WITH CHECK (driver_id = (SELECT id FROM drivers WHERE auth_user_id = auth.uid() LIMIT 1));

CREATE POLICY "driver_messages_update_own"
  ON public.driver_messages FOR UPDATE TO authenticated
  USING (driver_id = (SELECT id FROM drivers WHERE auth_user_id = auth.uid() LIMIT 1));

CREATE POLICY "driver_messages_service_role"
  ON public.driver_messages TO service_role USING (true);

-- ── DRIVER PAYOUTS table ─────────────────────────────────────

CREATE POLICY "driver_payouts_select_own"
  ON public.driver_payouts FOR SELECT TO authenticated
  USING (driver_id = (SELECT id FROM drivers WHERE auth_user_id = auth.uid() LIMIT 1));

CREATE POLICY "driver_payouts_service_role"
  ON public.driver_payouts TO service_role USING (true);

-- ── Revoke anon write access on sensitive tables ─────────────

REVOKE INSERT ON public.driver_sessions FROM anon;
REVOKE UPDATE ON public.driver_sessions FROM anon;
REVOKE DELETE ON public.driver_sessions FROM anon;

REVOKE INSERT ON public.driver_payouts  FROM anon;
REVOKE UPDATE ON public.driver_payouts  FROM anon;
REVOKE DELETE ON public.driver_payouts  FROM anon;

-- ── Verification ─────────────────────────────────────────────
-- SELECT tablename, rowsecurity FROM pg_tables
-- WHERE schemaname = 'public'
-- AND tablename IN ('drivers','loads','driver_sessions','driver_messages','driver_payouts');
-- All rows should show rowsecurity = true.

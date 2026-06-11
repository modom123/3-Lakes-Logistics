-- ============================================================
-- 3 Lakes Logistics — Row Level Security (custom PIN auth model)
--
-- This app uses a custom driver_login RPC, NOT Supabase Auth.
-- auth.uid() is always null for mobile clients.
-- Security model:
--   • Sensitive data (payouts, sessions) → service_role only via backend API
--   • Load board & messages → anon SELECT allowed (app uses anon key for realtime)
--   • All writes to sensitive tables → backend API only (service_role)
-- ============================================================

-- ── Enable RLS ───────────────────────────────────────────────

ALTER TABLE public.drivers         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loads           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.driver_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.driver_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.driver_payouts  ENABLE ROW LEVEL SECURITY;

-- ── Drop all existing policies (safe re-run) ─────────────────

DROP POLICY IF EXISTS driver_sessions_driver_access  ON public.driver_sessions;
DROP POLICY IF EXISTS driver_messages_driver_access  ON public.driver_messages;
DROP POLICY IF EXISTS driver_payouts_driver_access   ON public.driver_payouts;
DROP POLICY IF EXISTS "drivers_select_own"           ON public.drivers;
DROP POLICY IF EXISTS "drivers_update_own"           ON public.drivers;
DROP POLICY IF EXISTS "drivers_service_role"         ON public.drivers;
DROP POLICY IF EXISTS "loads_select_driver"          ON public.loads;
DROP POLICY IF EXISTS "loads_update_own"             ON public.loads;
DROP POLICY IF EXISTS "loads_service_role"           ON public.loads;
DROP POLICY IF EXISTS "driver_sessions_select_own"   ON public.driver_sessions;
DROP POLICY IF EXISTS "driver_sessions_delete_own"   ON public.driver_sessions;
DROP POLICY IF EXISTS "driver_sessions_service_role" ON public.driver_sessions;
DROP POLICY IF EXISTS "driver_messages_select_own"   ON public.driver_messages;
DROP POLICY IF EXISTS "driver_messages_insert_own"   ON public.driver_messages;
DROP POLICY IF EXISTS "driver_messages_update_own"   ON public.driver_messages;
DROP POLICY IF EXISTS "driver_messages_service_role" ON public.driver_messages;
DROP POLICY IF EXISTS "driver_payouts_select_own"    ON public.driver_payouts;
DROP POLICY IF EXISTS "driver_payouts_service_role"  ON public.driver_payouts;
DROP POLICY IF EXISTS "drivers_anon_select"          ON public.drivers;
DROP POLICY IF EXISTS "loads_anon_select"            ON public.loads;
DROP POLICY IF EXISTS "driver_messages_anon_select"  ON public.driver_messages;
DROP POLICY IF EXISTS "driver_messages_anon_insert"  ON public.driver_messages;

-- ── DRIVERS ──────────────────────────────────────────────────
-- Anon (mobile app with anon key) can read driver rows.
-- All writes go through the backend (service_role).

CREATE POLICY "drivers_anon_select"
  ON public.drivers FOR SELECT TO anon
  USING (true);

CREATE POLICY "drivers_service_role"
  ON public.drivers TO service_role
  USING (true);

-- ── LOADS ────────────────────────────────────────────────────
-- Anon can read loads that are available (booked) or already have a driver.
-- All writes (assign driver, status updates) go through backend.

CREATE POLICY "loads_anon_select"
  ON public.loads FOR SELECT TO anon
  USING (status IN ('booked', 'in_transit', 'delivered', 'completed'));

CREATE POLICY "loads_service_role"
  ON public.loads TO service_role
  USING (true);

-- ── DRIVER MESSAGES ──────────────────────────────────────────
-- Anon can read and insert messages (needed for realtime subscriptions).
-- The mobile app filters by driver_phone client-side.

CREATE POLICY "driver_messages_anon_select"
  ON public.driver_messages FOR SELECT TO anon
  USING (true);

CREATE POLICY "driver_messages_anon_insert"
  ON public.driver_messages FOR INSERT TO anon
  WITH CHECK (direction = 'outbound');

CREATE POLICY "driver_messages_service_role"
  ON public.driver_messages TO service_role
  USING (true);

-- ── DRIVER SESSIONS ──────────────────────────────────────────
-- Never accessed directly by the mobile app — backend API only.

CREATE POLICY "driver_sessions_service_role"
  ON public.driver_sessions TO service_role
  USING (true);

-- ── DRIVER PAYOUTS ───────────────────────────────────────────
-- Never accessed directly by the mobile app — backend API only.

CREATE POLICY "driver_payouts_service_role"
  ON public.driver_payouts TO service_role
  USING (true);

-- ── Revoke anon write access on sensitive tables ─────────────

REVOKE INSERT, UPDATE, DELETE ON public.driver_sessions FROM anon;
REVOKE INSERT, UPDATE, DELETE ON public.driver_payouts  FROM anon;

-- ── Verify ───────────────────────────────────────────────────
-- SELECT tablename, rowsecurity FROM pg_tables
-- WHERE schemaname = 'public'
-- AND tablename IN ('drivers','loads','driver_sessions','driver_messages','driver_payouts');
-- All rows should show rowsecurity = true.

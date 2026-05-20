-- ============================================================
-- 3 Lakes Logistics — Complete Database Setup with RLS & Grants
-- Run this after deploying driver_schema_additions.sql
-- ============================================================

-- Grant permissions on all new tables to roles
grant select on public.driver_messages to anon;
grant select, insert, update on public.driver_messages to authenticated;
grant select, insert, update, delete on public.driver_messages to service_role;

grant select on public.driver_sessions to anon;
grant select, insert, update, delete on public.driver_sessions to authenticated;
grant select, insert, update, delete on public.driver_sessions to service_role;

grant select on public.driver_payouts to anon;
grant select, insert, update on public.driver_payouts to authenticated;
grant select, insert, update, delete on public.driver_payouts to service_role;

grant select, update on public.drivers to anon;
grant select, update on public.drivers to authenticated;
grant select, update, delete on public.drivers to service_role;

grant select, update on public.loads to anon;
grant select, insert, update on public.loads to authenticated;
grant select, insert, update, delete on public.loads to service_role;

grant select, update on public.truck_telemetry to anon;
grant select, insert, update on public.truck_telemetry to authenticated;
grant select, insert, update, delete on public.truck_telemetry to service_role;

-- ============================================================
-- ENABLE ROW LEVEL SECURITY
-- ============================================================

alter table public.driver_messages enable row level security;
alter table public.driver_sessions enable row level security;
alter table public.driver_payouts enable row level security;

-- ============================================================
-- RLS POLICIES FOR DRIVER MESSAGES
-- ============================================================

-- Backend (service_role key) can do anything — bypasses RLS entirely.
-- Driver auth uses custom tokens stored in driver_sessions, not Supabase
-- auth, so there is no auth.uid() to build per-driver policies against.
create policy "driver_messages_service_role"
  on public.driver_messages
  to service_role
  using (true);

-- ============================================================
-- RLS POLICIES FOR DRIVER SESSIONS
-- ============================================================

create policy "driver_sessions_service_role"
  on public.driver_sessions
  to service_role
  using (true);

-- ============================================================
-- RLS POLICIES FOR DRIVER PAYOUTS
-- ============================================================

create policy "driver_payouts_service_role"
  on public.driver_payouts
  to service_role
  using (true);

-- ============================================================
-- VERIFY TABLES EXIST
-- ============================================================

-- Run these to verify all tables were created:
-- SELECT COUNT(*) FROM driver_messages;
-- SELECT COUNT(*) FROM driver_sessions;
-- SELECT COUNT(*) FROM driver_payouts;

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

-- Drivers can read their own messages
create policy "driver_messages_select_own"
  on public.driver_messages
  for select to authenticated
  using (driver_id = (select id from drivers where auth_user_id = auth.uid() limit 1));

-- Drivers can insert their own messages
create policy "driver_messages_insert_own"
  on public.driver_messages
  for insert to authenticated
  with check (driver_id = (select id from drivers where auth_user_id = auth.uid() limit 1));

-- Service role (backend) can do anything
create policy "driver_messages_service_role"
  on public.driver_messages
  to service_role
  using (true);

-- ============================================================
-- RLS POLICIES FOR DRIVER SESSIONS
-- ============================================================

-- Drivers can read their own sessions
create policy "driver_sessions_select_own"
  on public.driver_sessions
  for select to authenticated
  using (driver_id = (select id from drivers where auth_user_id = auth.uid() limit 1));

-- Service role (backend) can do anything
create policy "driver_sessions_service_role"
  on public.driver_sessions
  to service_role
  using (true);

-- ============================================================
-- RLS POLICIES FOR DRIVER PAYOUTS
-- ============================================================

-- Drivers can read their own payouts
create policy "driver_payouts_select_own"
  on public.driver_payouts
  for select to authenticated
  using (driver_id = (select id from drivers where auth_user_id = auth.uid() limit 1));

-- Service role (backend) can do anything
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

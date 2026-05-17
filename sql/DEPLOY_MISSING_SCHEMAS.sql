-- ============================================================
-- 3 Lakes Logistics — Deploy All Missing Schemas
-- Run this ONE script in Supabase SQL Editor to unblock launch.
--
-- What this deploys:
--   Part A: Email ingest pipeline (email_log, email_templates, email_attachments)
--   Part B: Driver mobile app tables (driver_messages, driver_sessions, driver_payouts)
--            + missing columns on drivers and loads tables
--
-- Safe to re-run: all statements use IF NOT EXISTS / ON CONFLICT DO NOTHING
-- Prerequisites: full_sync_migration.sql must already be deployed (loads + drivers tables exist)
-- ============================================================

-- ============================================================
-- PART A: Email Ingest Pipeline Schema (email_schema.sql)
-- ============================================================

CREATE TABLE IF NOT EXISTS email_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_email text NOT NULL,
    to_email text NOT NULL,
    subject text,
    body_text text,
    body_html text,
    attachment_count int DEFAULT 0,
    status text DEFAULT 'received',
    confidence numeric,
    extracted_data jsonb,
    source text DEFAULT 'sendgrid',
    broker_name text,
    load_id uuid REFERENCES loads(id) ON DELETE SET NULL,
    notes text,
    received_at timestamptz DEFAULT now(),
    processed_at timestamptz,
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_email_log_status ON email_log(status);
CREATE INDEX IF NOT EXISTS idx_email_log_broker ON email_log(broker_name);
CREATE INDEX IF NOT EXISTS idx_email_log_load ON email_log(load_id);
CREATE INDEX IF NOT EXISTS idx_email_log_received ON email_log(received_at DESC);

ALTER TABLE email_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY email_log_read_policy ON email_log FOR SELECT
  USING (auth.role() = 'authenticated');

CREATE TABLE IF NOT EXISTS email_templates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    subject text NOT NULL,
    body_html text NOT NULL,
    body_text text,
    variables text[],
    usage_count int DEFAULT 0,
    last_used_at timestamptz,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

INSERT INTO email_templates (name, subject, body_html, body_text, variables) VALUES
(
    'dispatch_sheet',
    'Load {{load_number}} — {{origin_city}} to {{dest_city}}',
    '<html><body><h2>Load Accepted</h2><p><strong>Driver:</strong> {{driver_name}}</p><p><strong>Load Number:</strong> {{load_number}}</p><p><strong>Route:</strong> {{origin_city}}, {{origin_state}} to {{dest_city}}, {{dest_state}}</p><p><strong>Rate:</strong> ${{rate_total}}</p><p><strong>Pickup:</strong> {{pickup_address}} at {{pickup_time}}</p><p><strong>Delivery:</strong> {{delivery_address}} at {{delivery_time}}</p><p>Safe travels!</p></body></html>',
    'Load {{load_number}} Accepted\nDriver: {{driver_name}}\nRoute: {{origin_city}}, {{origin_state}} to {{dest_city}}, {{dest_state}}\nRate: ${{rate_total}}\nPickup: {{pickup_address}} at {{pickup_time}}\nDelivery: {{delivery_address}} at {{delivery_time}}',
    ARRAY['driver_name','load_number','origin_city','origin_state','dest_city','dest_state','rate_total','pickup_address','pickup_time','delivery_address','delivery_time']
),
(
    'broker_confirm',
    'Load {{load_number}} Assigned — {{driver_name}}',
    '<html><body><h2>Driver Assigned</h2><p><strong>Broker:</strong> {{broker_name}}</p><p><strong>Driver:</strong> {{driver_name}}</p><p><strong>Load:</strong> {{load_number}}</p><p><strong>Pickup:</strong> {{pickup_at}}</p><p><strong>Delivery Target:</strong> {{delivery_by}}</p><p>Driver has been notified and is en route to pickup.</p></body></html>',
    'Driver Assigned\nBroker: {{broker_name}}\nDriver: {{driver_name}}\nLoad: {{load_number}}\nPickup: {{pickup_at}}\nDelivery Target: {{delivery_by}}',
    ARRAY['broker_name','driver_name','load_number','pickup_at','delivery_by']
),
(
    'payout_summary',
    'Your Weekly Earnings — {{week_ending}}',
    '<html><body><h2>Weekly Payout Summary</h2><p><strong>Week Ending:</strong> {{week_ending}}</p><p><strong>Total Loads:</strong> {{load_count}}</p><p><strong>Gross Revenue:</strong> ${{gross_revenue}}</p><p><strong>Fees & Deductions:</strong> -${{total_deductions}}</p><p><strong>Net Payout:</strong> <strong>${{net_payout}}</strong></p><p>Payout scheduled for {{payout_date}}.</p></body></html>',
    'Weekly Payout Summary\nWeek Ending: {{week_ending}}\nTotal Loads: {{load_count}}\nGross Revenue: ${{gross_revenue}}\nFees & Deductions: -${{total_deductions}}\nNet Payout: ${{net_payout}}\nPayout scheduled for {{payout_date}}.',
    ARRAY['week_ending','load_count','gross_revenue','total_deductions','net_payout','payout_date']
) ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS email_attachments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email_log_id uuid NOT NULL REFERENCES email_log(id) ON DELETE CASCADE,
    filename text NOT NULL,
    mime_type text,
    file_size int,
    storage_url text,
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_email_attachments_email ON email_attachments(email_log_id);

-- ============================================================
-- PART B: Driver Mobile App Schema (driver_schema_additions.sql)
-- ============================================================

CREATE TABLE IF NOT EXISTS driver_messages (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  driver_phone text NOT NULL,
  direction text NOT NULL CHECK (direction IN ('inbound', 'outbound')),
  body text NOT NULL,
  msg_type text DEFAULT 'text' CHECK (msg_type IN ('text', 'load_offer')),
  driver_id uuid REFERENCES drivers(id) ON DELETE SET NULL,
  load_id uuid REFERENCES loads(id) ON DELETE SET NULL,
  read boolean DEFAULT false,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_driver_messages_phone_created ON driver_messages(driver_phone, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_driver_messages_driver_id ON driver_messages(driver_id);
CREATE INDEX IF NOT EXISTS idx_driver_messages_load_id ON driver_messages(load_id);

CREATE TABLE IF NOT EXISTS driver_sessions (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  driver_id uuid NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
  token text UNIQUE NOT NULL,
  expires_at timestamptz NOT NULL,
  last_activity_at timestamptz DEFAULT now(),
  ip_address text,
  user_agent text,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_driver_sessions_token ON driver_sessions(token);
CREATE INDEX IF NOT EXISTS idx_driver_sessions_driver_id ON driver_sessions(driver_id);
CREATE INDEX IF NOT EXISTS idx_driver_sessions_expires_at ON driver_sessions(expires_at);

CREATE TABLE IF NOT EXISTS driver_payouts (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  driver_id uuid NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
  load_id uuid REFERENCES loads(id) ON DELETE SET NULL,
  amount_cents integer NOT NULL CHECK (amount_cents > 0),
  dispatch_fee_cents integer DEFAULT 0,
  insurance_cents integer DEFAULT 0,
  net_cents integer NOT NULL,
  stripe_transfer_id text,
  stripe_charge_id text,
  status text DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'paid', 'failed', 'cancelled')),
  failure_reason text,
  requested_at timestamptz DEFAULT now(),
  processed_at timestamptz,
  paid_at timestamptz,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_driver_payouts_driver_id ON driver_payouts(driver_id);
CREATE INDEX IF NOT EXISTS idx_driver_payouts_status ON driver_payouts(status);
CREATE INDEX IF NOT EXISTS idx_driver_payouts_load_id ON driver_payouts(load_id);

-- Missing columns on loads table
ALTER TABLE loads ADD COLUMN IF NOT EXISTS pickup_address text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS delivery_address text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS broker_phone text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS special_instructions text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS weight numeric;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS equipment_type text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS post_to_website boolean DEFAULT false;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS delivered_at timestamptz;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS driver_id uuid REFERENCES drivers(id) ON DELETE SET NULL;

-- Missing columns on drivers table
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS pin_hash text;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS stripe_account_id text;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS stripe_account_status text DEFAULT 'not_connected' CHECK (stripe_account_status IN ('not_connected', 'pending', 'connected', 'failed'));
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS fcm_token text;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS phone_e164 text;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS app_version text;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS last_location jsonb;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS last_location_at timestamptz;

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_loads_driver_id ON loads(driver_id);
CREATE INDEX IF NOT EXISTS idx_loads_status_pickup_at ON loads(status, pickup_at DESC);
CREATE INDEX IF NOT EXISTS idx_drivers_phone_e164 ON drivers(phone_e164);
CREATE INDEX IF NOT EXISTS idx_loads_delivered_at ON loads(delivered_at DESC);
CREATE INDEX IF NOT EXISTS idx_truck_telemetry_driver_truck_ts ON truck_telemetry(carrier_id, truck_id, ts DESC);

-- Row Level Security on sensitive driver tables
ALTER TABLE driver_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE driver_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE driver_payouts ENABLE ROW LEVEL SECURITY;

CREATE POLICY driver_sessions_driver_access ON driver_sessions
  FOR SELECT USING (driver_id::text = current_setting('app.current_driver_id', true));

CREATE POLICY driver_messages_driver_access ON driver_messages
  FOR SELECT USING (driver_id::text = current_setting('app.current_driver_id', true));

CREATE POLICY driver_payouts_driver_access ON driver_payouts
  FOR SELECT USING (driver_id::text = current_setting('app.current_driver_id', true));

-- Grant anon role access (for PWA token-based access)
GRANT SELECT ON driver_messages TO anon;
GRANT SELECT ON driver_payouts TO anon;
GRANT INSERT ON driver_messages TO anon;
GRANT UPDATE ON driver_messages TO anon;

-- ============================================================
-- VERIFICATION — run these after deployment to confirm success
-- ============================================================
-- SELECT COUNT(*) FROM email_log;        -- should return 0 (empty, no error)
-- SELECT COUNT(*) FROM driver_messages;  -- should return 0
-- SELECT COUNT(*) FROM driver_sessions;  -- should return 0
-- SELECT COUNT(*) FROM driver_payouts;   -- should return 0
-- SELECT stripe_account_id FROM drivers LIMIT 1;   -- new column, no error
-- SELECT pickup_address FROM loads LIMIT 1;        -- new column, no error

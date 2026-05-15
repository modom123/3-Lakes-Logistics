-- Phase 9: Database Schema Additions for Driver Mobile App
-- Step 82-89: Create missing tables and add fields

-- Step 82: Create driver_messages table (used by routes_comms.py but missing)
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

-- Step 83: Create driver_sessions table (JWT/token storage)
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

-- Step 84: Create driver_payouts table (Stripe Connect payouts)
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

-- Step 85-88: Add missing fields to loads table
ALTER TABLE loads ADD COLUMN IF NOT EXISTS pickup_address text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS delivery_address text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS broker_phone text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS special_instructions text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS weight numeric;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS equipment_type text;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS post_to_website boolean DEFAULT false;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS delivered_at timestamptz;
ALTER TABLE loads ADD COLUMN IF NOT EXISTS driver_id uuid REFERENCES drivers(id) ON DELETE SET NULL;

-- Step 85: Add fields to drivers table for Stripe & notifications
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS pin_hash text;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS stripe_account_id text;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS stripe_account_status text DEFAULT 'not_connected' CHECK (stripe_account_status IN ('not_connected', 'pending', 'connected', 'failed'));
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS fcm_token text;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS phone_e164 text;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS app_version text;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS last_location jsonb;
ALTER TABLE drivers ADD COLUMN IF NOT EXISTS last_location_at timestamptz;

-- Create indexes for better query performance (Step 89)
CREATE INDEX IF NOT EXISTS idx_loads_driver_id ON loads(driver_id);
CREATE INDEX IF NOT EXISTS idx_loads_status_pickup_at ON loads(status, pickup_at DESC);
CREATE INDEX IF NOT EXISTS idx_drivers_phone_e164 ON drivers(phone_e164);
CREATE INDEX IF NOT EXISTS idx_loads_delivered_at ON loads(delivered_at DESC);
CREATE INDEX IF NOT EXISTS idx_truck_telemetry_driver_truck_ts ON truck_telemetry(carrier_id, truck_id, ts DESC);

-- Enable RLS (Row Level Security) on sensitive tables
ALTER TABLE driver_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE driver_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE driver_payouts ENABLE ROW LEVEL SECURITY;

-- Basic RLS policies (will be enforced via JWT driver_id)
CREATE POLICY driver_sessions_driver_access ON driver_sessions
  FOR SELECT USING (driver_id::text = current_setting('app.current_driver_id', true));

CREATE POLICY driver_messages_driver_access ON driver_messages
  FOR SELECT USING (driver_id::text = current_setting('app.current_driver_id', true));

CREATE POLICY driver_payouts_driver_access ON driver_payouts
  FOR SELECT USING (driver_id::text = current_setting('app.current_driver_id', true));

-- Grant permissions to anon role (for PWA access with token)
GRANT SELECT ON driver_messages TO anon;
GRANT SELECT ON driver_payouts TO anon;
GRANT INSERT ON driver_messages TO anon;
GRANT UPDATE ON driver_messages TO anon;

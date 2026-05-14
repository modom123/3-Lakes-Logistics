-- 3 Lakes Driver App Tables
-- Run this in Supabase SQL Editor: https://zngipootstubwvgdmckt.supabase.co/project/default/sql

-- Drivers table
CREATE TABLE IF NOT EXISTS drivers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone TEXT UNIQUE NOT NULL,
  pin TEXT NOT NULL,
  name TEXT NOT NULL,
  email TEXT,
  status TEXT DEFAULT 'active',
  hos_drive_remaining_hours DECIMAL(5,2) DEFAULT 11,
  hos_shift_remaining_hours DECIMAL(5,2) DEFAULT 14,
  hos_cycle_remaining_hours DECIMAL(5,2) DEFAULT 70,
  current_load_id UUID,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Dispatchers table
CREATE TABLE IF NOT EXISTS dispatchers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Loads table
CREATE TABLE IF NOT EXISTS loads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  load_number TEXT UNIQUE NOT NULL,
  status TEXT DEFAULT 'booked',
  origin_city TEXT NOT NULL,
  origin_state TEXT NOT NULL,
  origin_address TEXT,
  dest_city TEXT NOT NULL,
  dest_state TEXT NOT NULL,
  dest_address TEXT,
  commodity TEXT,
  weight DECIMAL(10,2),
  miles DECIMAL(8,1) NOT NULL,
  rate_total DECIMAL(10,2) NOT NULL,
  pickup_at TIMESTAMPTZ NOT NULL,
  delivery_at TIMESTAMPTZ,
  broker_name TEXT,
  broker_phone TEXT,
  special_instructions TEXT,
  dispatcher_id UUID REFERENCES dispatchers(id),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Driver Earnings table
CREATE TABLE IF NOT EXISTS driver_earnings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_id UUID NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
  load_id UUID NOT NULL REFERENCES loads(id) ON DELETE CASCADE,
  gross_pay DECIMAL(10,2) NOT NULL,
  dispatch_fee DECIMAL(10,2),
  fuel_advance DECIMAL(10,2),
  insurance_deduction DECIMAL(10,2),
  net_pay DECIMAL(10,2),
  paid_at TIMESTAMPTZ,
  status TEXT DEFAULT 'unpaid',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Driver Messages table
CREATE TABLE IF NOT EXISTS driver_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_id UUID NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
  dispatcher_id UUID REFERENCES dispatchers(id),
  direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
  body TEXT NOT NULL,
  msg_type TEXT DEFAULT 'text',
  load_id UUID REFERENCES loads(id),
  read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Driver Documents table
CREATE TABLE IF NOT EXISTS driver_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_id UUID NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
  load_id UUID REFERENCES loads(id),
  document_type TEXT NOT NULL,
  file_url TEXT NOT NULL,
  file_name TEXT,
  file_size INT,
  uploaded_at TIMESTAMPTZ DEFAULT now(),
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Enable Row Level Security
ALTER TABLE drivers ENABLE ROW LEVEL SECURITY;
ALTER TABLE loads ENABLE ROW LEVEL SECURITY;
ALTER TABLE driver_earnings ENABLE ROW LEVEL SECURITY;
ALTER TABLE driver_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE driver_documents ENABLE ROW LEVEL SECURITY;

-- Policies: Drivers can only see their own data
CREATE POLICY "Drivers see own data" ON drivers
  FOR SELECT USING (auth.uid()::text = id::text);

CREATE POLICY "Drivers see own loads" ON loads
  FOR SELECT USING (true); -- Loads are public, drivers pick from available

CREATE POLICY "Drivers see own earnings" ON driver_earnings
  FOR SELECT USING (auth.uid()::text = driver_id::text);

CREATE POLICY "Drivers see own messages" ON driver_messages
  FOR SELECT USING (auth.uid()::text = driver_id::text);

CREATE POLICY "Drivers see own documents" ON driver_documents
  FOR SELECT USING (auth.uid()::text = driver_id::text);

-- Insert demo dispatcher
INSERT INTO dispatchers (name, email, phone) VALUES
  ('John Martinez', 'dispatch@3lakes.com', '(312) 555-0911')
ON CONFLICT DO NOTHING;

-- Insert demo driver (James Thompson)
INSERT INTO drivers (phone, pin, name, email, status) VALUES
  ('+13125550100', '1234', 'James Thompson', 'james@driver.local', 'active')
ON CONFLICT (phone) DO NOTHING;

-- Insert demo loads
INSERT INTO loads (load_number, status, origin_city, origin_state, dest_city, dest_state, commodity, miles, rate_total, pickup_at, broker_name, broker_phone) VALUES
  ('LD-2848', 'booked', 'Dallas', 'TX', 'Atlanta', 'GA', 'Electronics', 781, 1850, now() + interval '1 day', 'XPO Logistics', '(800) 438-6822'),
  ('LD-2849', 'booked', 'Denver', 'CO', 'Phoenix', 'AZ', 'Auto Parts', 602, 980, now() + interval '2 days', 'JB Hunt', '(800) 721-8246'),
  ('LD-2850', 'booked', 'Memphis', 'TN', 'Miami', 'FL', 'Produce', 1100, 2340, now() + interval '3 days', 'Schneider', '(800) 558-9844')
ON CONFLICT (load_number) DO NOTHING;

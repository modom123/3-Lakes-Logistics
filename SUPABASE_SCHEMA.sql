-- 3 Lakes Driver App - Table Schema Only

CREATE TABLE drivers (
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

CREATE TABLE dispatchers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE loads (
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

CREATE TABLE driver_earnings (
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

CREATE TABLE driver_messages (
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

CREATE TABLE driver_documents (
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

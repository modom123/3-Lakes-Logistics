-- =============================================================================
-- Light Fleet Module — SUV/Car services for 3 Lakes Logistics
-- Service types: NEMT, Executive Transport, Courier/Last-Mile, Gig Fleet
-- =============================================================================

-- light_vehicle_trips: the core trip record for all 4 service types
CREATE TABLE IF NOT EXISTS light_vehicle_trips (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_type text NOT NULL CHECK (trip_type IN ('nemt','executive','courier','gig')),
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','assigned','in_progress','completed','cancelled')),
  driver_id uuid,

  -- pickup/dropoff
  pickup_address text NOT NULL,
  pickup_lat numeric(9,6),
  pickup_lng numeric(9,6),
  dropoff_address text NOT NULL,
  dropoff_lat numeric(9,6),
  dropoff_lng numeric(9,6),
  scheduled_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,

  -- rate
  rate_total numeric(10,2),
  rate_per_mile numeric(6,2),
  estimated_miles numeric(8,2),

  -- passenger/client
  passenger_name text,
  passenger_phone text,

  -- NEMT fields
  nemt_client_id uuid,
  medical_necessity_code text,
  insurance_auth_number text,
  insurance_provider text,
  mobility_needs text CHECK (mobility_needs IN ('ambulatory','wheelchair','stretcher') OR mobility_needs IS NULL),

  -- Executive fields
  executive_account_id uuid,
  flight_number text,
  vehicle_class text CHECK (vehicle_class IN ('suv','sedan','luxury') OR vehicle_class IS NULL),

  -- Courier fields
  package_count int DEFAULT 0,
  package_weight_lbs numeric(8,2),
  pod_url text,

  -- notes
  notes text,
  dispatcher_notes text,

  -- External platform fields (Curri, Roadie, etc.)
  external_id text,        -- order/gig ID from the source platform
  source text,             -- 'curri' | 'roadie' | 'internal' | 'nemt_clients_table' etc.
  driver_payout numeric(10,2),
  platform_fee numeric(10,2),
  settled_at timestamptz,
  assigned_at timestamptz,
  auth_logged_at timestamptz,

  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Index for common list/filter patterns
CREATE INDEX IF NOT EXISTS idx_lvt_trip_type   ON light_vehicle_trips (trip_type);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lvt_external_id ON light_vehicle_trips (external_id) WHERE external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_lvt_status       ON light_vehicle_trips (status);
CREATE INDEX IF NOT EXISTS idx_lvt_driver_id    ON light_vehicle_trips (driver_id);
CREATE INDEX IF NOT EXISTS idx_lvt_completed_at ON light_vehicle_trips (completed_at);
CREATE INDEX IF NOT EXISTS idx_lvt_scheduled_at ON light_vehicle_trips (scheduled_at DESC);
CREATE INDEX IF NOT EXISTS idx_lvt_nemt_client  ON light_vehicle_trips (nemt_client_id);
CREATE INDEX IF NOT EXISTS idx_lvt_exec_account ON light_vehicle_trips (executive_account_id);

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION light_fleet_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_lvt_updated_at
  BEFORE UPDATE ON light_vehicle_trips
  FOR EACH ROW EXECUTE FUNCTION light_fleet_set_updated_at();


-- light_vehicle_drivers: car/SUV drivers (no CDL required, MVR mandatory)
CREATE TABLE IF NOT EXISTS light_vehicle_drivers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  phone text,
  email text,
  license_number text,
  license_state text,
  license_expires date,
  mvr_status text DEFAULT 'pending' CHECK (mvr_status IN ('pending','clear','flagged')),
  mvr_checked_at timestamptz,
  background_check_status text DEFAULT 'pending' CHECK (background_check_status IN ('pending','clear','flagged')),

  -- vehicle they drive
  vehicle_type text CHECK (vehicle_type IN ('suv','sedan','cargo_van','luxury')),
  vehicle_year int,
  vehicle_make text,
  vehicle_model text,
  vehicle_plate text,
  vehicle_insurance_expires date,

  -- service types they are approved for (array of trip_type values)
  approved_services text[] DEFAULT '{}',

  -- performance
  status text DEFAULT 'active' CHECK (status IN ('active','inactive','suspended')),
  rating numeric(3,2),
  total_trips int DEFAULT 0,

  -- billing plan (determines platform fee rate)
  plan text DEFAULT 'starter' CHECK (plan IN ('starter','pro_fleet','add_on')),

  -- intake fields (from self-service signup form)
  location text,
  clean_record boolean DEFAULT true,
  has_insurance boolean DEFAULT true,
  referral_source text,
  notes text,
  onboarded_at timestamptz,

  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lvd_status       ON light_vehicle_drivers (status);
CREATE INDEX IF NOT EXISTS idx_lvd_vehicle_type ON light_vehicle_drivers (vehicle_type);
CREATE INDEX IF NOT EXISTS idx_lvd_mvr_status   ON light_vehicle_drivers (mvr_status);

CREATE OR REPLACE TRIGGER trg_lvd_updated_at
  BEFORE UPDATE ON light_vehicle_drivers
  FOR EACH ROW EXECUTE FUNCTION light_fleet_set_updated_at();


-- nemt_clients: repeat medical transport patients
CREATE TABLE IF NOT EXISTS nemt_clients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  dob date,
  phone text,
  address text,
  insurance_provider text,
  insurance_id text,
  mobility_needs text CHECK (mobility_needs IN ('ambulatory','wheelchair','stretcher') OR mobility_needs IS NULL),
  notes text,
  total_trips int DEFAULT 0,
  status text DEFAULT 'active' CHECK (status IN ('active','inactive')),
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nemt_clients_status ON nemt_clients (status);
CREATE INDEX IF NOT EXISTS idx_nemt_clients_name   ON nemt_clients (name);


-- executive_accounts: corporate clients for executive/VIP transport
CREATE TABLE IF NOT EXISTS executive_accounts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_name text NOT NULL,
  contact_name text,
  contact_phone text,
  contact_email text,
  billing_type text DEFAULT 'invoice' CHECK (billing_type IN ('invoice','card','account')),
  rate_per_mile numeric(6,2),
  flat_rate_airport numeric(8,2),
  contract_expires date,
  status text DEFAULT 'active' CHECK (status IN ('active','inactive')),
  total_trips int DEFAULT 0,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_exec_accounts_status ON executive_accounts (status);

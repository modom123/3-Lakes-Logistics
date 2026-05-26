-- Migration 033: Bill of Lading (BOL) Generator
-- Run in Supabase SQL editor

CREATE TABLE IF NOT EXISTS public.bols (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  load_id             uuid REFERENCES loads(id) ON DELETE SET NULL,
  bol_number          text NOT NULL,              -- e.g. BOL-2026-0042
  -- Shipper (origin)
  shipper_name        text,
  shipper_address     text,
  shipper_city        text,
  shipper_state       text,
  shipper_zip         text,
  shipper_phone       text,
  -- Consignee (destination)
  consignee_name      text,
  consignee_address   text,
  consignee_city      text,
  consignee_state     text,
  consignee_zip       text,
  consignee_phone     text,
  -- Carrier
  carrier_name        text,
  carrier_mc          text,
  carrier_dot         text,
  trailer_number      text,
  -- Load
  pro_number          text,                       -- = load_number
  pickup_date         date,
  delivery_date       date,
  origin_city         text,
  origin_state        text,
  dest_city           text,
  dest_state          text,
  -- Freight
  commodity           text,
  num_pieces          integer,
  package_type        text DEFAULT 'Pallet',
  weight_lbs          numeric,
  hazmat              boolean DEFAULT false,
  temperature_req     text,                       -- reefer temp if applicable
  special_instructions text,
  -- Status
  status              text DEFAULT 'draft' CHECK (status IN ('draft','sent','signed')),
  notes               text,
  created_at          timestamptz DEFAULT now(),
  updated_at          timestamptz DEFAULT now()
);

ALTER TABLE public.bols ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full_bols" ON public.bols
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_bols_load   ON public.bols(load_id);
CREATE INDEX IF NOT EXISTS idx_bols_status ON public.bols(status);
CREATE INDEX IF NOT EXISTS idx_bols_num    ON public.bols(bol_number);

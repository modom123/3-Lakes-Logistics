-- Migration 030: Driver Settlements + Shippers/Brokers CRM
-- Run in Supabase SQL editor

-- ── Driver Settlements ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.driver_settlements (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  carrier_id          uuid REFERENCES active_carriers(id) ON DELETE SET NULL,
  carrier_name        text,
  load_id             uuid REFERENCES loads(id) ON DELETE SET NULL,
  load_number         text,
  week_ending         date,
  miles               numeric,
  gross_pay           numeric NOT NULL,
  dispatch_fee        numeric NOT NULL,
  dispatch_pct        numeric DEFAULT 8,
  insurance_deduction numeric DEFAULT 45,
  other_deductions    numeric DEFAULT 0,
  net_pay             numeric NOT NULL,
  status              text DEFAULT 'pending' CHECK (status IN ('pending','sent','paid')),
  notes               text,
  created_at          timestamptz DEFAULT now()
);

ALTER TABLE public.driver_settlements ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full_settlements" ON public.driver_settlements
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_settlements_carrier ON public.driver_settlements(carrier_id);
CREATE INDEX IF NOT EXISTS idx_settlements_week    ON public.driver_settlements(week_ending DESC);

-- ── Shippers / Brokers CRM ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.shippers (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_name   text NOT NULL,
  shipper_type   text DEFAULT 'broker' CHECK (shipper_type IN ('broker','shipper','3pl')),
  status         text DEFAULT 'active' CHECK (status IN ('active','preferred','inactive','do_not_use')),
  mc_number      text,
  dot_number     text,
  contact_name   text,
  email          text,
  phone          text,
  payment_terms  text DEFAULT 'net_30',
  credit_limit   numeric,
  total_loads    integer DEFAULT 0,
  total_revenue  numeric DEFAULT 0,
  notes          text,
  created_at     timestamptz DEFAULT now(),
  updated_at     timestamptz DEFAULT now()
);

ALTER TABLE public.shippers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full_shippers" ON public.shippers
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_shippers_name   ON public.shippers(company_name);
CREATE INDEX IF NOT EXISTS idx_shippers_status ON public.shippers(status);

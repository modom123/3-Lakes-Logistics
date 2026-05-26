-- Migration 031: Invoice Factoring + AR Aging Support
-- Run in Supabase SQL editor

-- ── Invoice Factoring Submissions ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.factoring_submissions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id      uuid REFERENCES invoices(id) ON DELETE SET NULL,
  invoice_number  text,
  invoice_amount  numeric NOT NULL,
  factor_company  text NOT NULL,           -- 'OTR Capital', 'Triumph Business Capital', 'RTS Financial'
  fee_pct         numeric DEFAULT 3,
  advance_pct     numeric DEFAULT 95,
  advance_amount  numeric NOT NULL,
  factoring_fee   numeric NOT NULL,
  reserve_amount  numeric,
  funding_date    date,
  settled_at      timestamptz,
  status          text DEFAULT 'submitted'
                  CHECK (status IN ('submitted','advanced','settled','rejected')),
  notes           text,
  created_at      timestamptz DEFAULT now()
);

ALTER TABLE public.factoring_submissions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full_factoring" ON public.factoring_submissions
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_factoring_invoice ON public.factoring_submissions(invoice_id);
CREATE INDEX IF NOT EXISTS idx_factoring_status  ON public.factoring_submissions(status);
CREATE INDEX IF NOT EXISTS idx_factoring_company ON public.factoring_submissions(factor_company);

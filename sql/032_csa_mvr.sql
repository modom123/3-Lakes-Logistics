-- Migration 032: CSA Safety Scores + Driver MVR Records
-- Run in Supabase SQL editor

-- ── Carrier CSA / BASIC Safety Scores ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.carrier_csa_scores (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  carrier_id        uuid REFERENCES active_carriers(id) ON DELETE SET NULL,
  carrier_name      text,
  safety_rating     text DEFAULT 'None',   -- Satisfactory | Conditional | Unsatisfactory | None
  operating_status  text DEFAULT 'AUTHORIZED', -- AUTHORIZED | NOT AUTHORIZED | OUT OF SERVICE
  review_date       date,
  oos_date          date,
  -- BASIC SMS percentile scores (0–100, null = no data)
  score_unsafe      numeric,   -- Unsafe Driving         threshold 65
  score_hos         numeric,   -- Hours-of-Service        threshold 65
  score_fitness     numeric,   -- Driver Fitness          threshold 80
  score_substances  numeric,   -- Controlled Substances   threshold 80
  score_maintenance numeric,   -- Vehicle Maintenance     threshold 80
  score_hm          numeric,   -- Hazardous Materials     threshold 80
  score_crash       numeric,   -- Crash Indicator         threshold 65
  oos_pct           numeric,   -- OOS inspection %
  notes             text,
  created_at        timestamptz DEFAULT now(),
  updated_at        timestamptz DEFAULT now()
);

ALTER TABLE public.carrier_csa_scores ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full_csa" ON public.carrier_csa_scores
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_csa_carrier  ON public.carrier_csa_scores(carrier_id);
CREATE INDEX IF NOT EXISTS idx_csa_rating   ON public.carrier_csa_scores(safety_rating);
CREATE INDEX IF NOT EXISTS idx_csa_op       ON public.carrier_csa_scores(operating_status);

-- ── Driver MVR Records ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.driver_mvr_records (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  driver_id      uuid REFERENCES active_carriers(id) ON DELETE SET NULL,
  driver_name    text NOT NULL,
  check_date     date NOT NULL,
  result         text DEFAULT 'clean' CHECK (result IN ('clean','minor','major','suspended')),
  violations     integer DEFAULT 0,
  cdl_class      text DEFAULT 'A',
  cdl_expires    date,
  endorsements   text,
  next_check_due date,
  notes          text,
  created_at     timestamptz DEFAULT now(),
  updated_at     timestamptz DEFAULT now()
);

ALTER TABLE public.driver_mvr_records ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full_mvr" ON public.driver_mvr_records
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_mvr_driver   ON public.driver_mvr_records(driver_id);
CREATE INDEX IF NOT EXISTS idx_mvr_result   ON public.driver_mvr_records(result);
CREATE INDEX IF NOT EXISTS idx_mvr_next_due ON public.driver_mvr_records(next_check_due);

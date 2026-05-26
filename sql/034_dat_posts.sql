-- Migration 034: DAT Load Board — Truck Postings
-- Run in Supabase SQL editor

CREATE TABLE IF NOT EXISTS public.dat_truck_posts (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  carrier_id       uuid REFERENCES active_carriers(id) ON DELETE SET NULL,
  carrier_name     text NOT NULL,
  equipment_type   text NOT NULL,         -- Dry Van 53', Reefer, Flatbed, etc.
  available_date   date NOT NULL,
  origin_zip       text,
  origin_city      text,
  origin_state     text,
  dest_city        text,                  -- preferred destination (optional)
  dest_state       text,
  contact_name     text,
  contact_phone    text,
  rate_min         numeric,               -- minimum rate carrier will accept
  miles_willing    integer DEFAULT 500,   -- max deadhead miles willing to run
  notes            text,
  posted_to_dat    boolean DEFAULT false,
  dat_post_id      text,                  -- DAT's internal posting ID (when live)
  status           text DEFAULT 'active'
                   CHECK (status IN ('active','expired','cancelled')),
  expires_at       timestamptz,
  created_at       timestamptz DEFAULT now(),
  updated_at       timestamptz DEFAULT now()
);

ALTER TABLE public.dat_truck_posts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full_dat_posts" ON public.dat_truck_posts
  FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_dat_posts_carrier  ON public.dat_truck_posts(carrier_id);
CREATE INDEX IF NOT EXISTS idx_dat_posts_status   ON public.dat_truck_posts(status);
CREATE INDEX IF NOT EXISTS idx_dat_posts_avail    ON public.dat_truck_posts(available_date);
CREATE INDEX IF NOT EXISTS idx_dat_posts_equip    ON public.dat_truck_posts(equipment_type);

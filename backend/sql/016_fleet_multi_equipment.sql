-- Part 1: Add summary columns to active_carriers
ALTER TABLE public.active_carriers
  ADD COLUMN IF NOT EXISTS fleet_size      int,
  ADD COLUMN IF NOT EXISTS equipment_types text[];

-- Backfill from existing trailer_type (single value → 1-element array)
UPDATE public.active_carriers
SET equipment_types = ARRAY[trailer_type]
WHERE trailer_type IS NOT NULL
  AND (equipment_types IS NULL OR equipment_types = '{}');

-- Part 2: Sync trigger — keep fleet_size and equipment_types current whenever fleet_assets changes
CREATE OR REPLACE FUNCTION sync_carrier_fleet_summary()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  UPDATE public.active_carriers
  SET
    fleet_size      = (SELECT COUNT(*) FROM public.fleet_assets WHERE carrier_id = COALESCE(NEW.carrier_id, OLD.carrier_id)),
    equipment_types = (SELECT ARRAY_AGG(DISTINCT trailer_type) FROM public.fleet_assets WHERE carrier_id = COALESCE(NEW.carrier_id, OLD.carrier_id) AND trailer_type IS NOT NULL),
    trailer_type    = (SELECT trailer_type FROM public.fleet_assets WHERE carrier_id = COALESCE(NEW.carrier_id, OLD.carrier_id) ORDER BY created_at LIMIT 1)
  WHERE id = COALESCE(NEW.carrier_id, OLD.carrier_id);
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_fleet_summary ON public.fleet_assets;
CREATE TRIGGER trg_fleet_summary
AFTER INSERT OR UPDATE OR DELETE ON public.fleet_assets
FOR EACH ROW EXECUTE FUNCTION sync_carrier_fleet_summary();

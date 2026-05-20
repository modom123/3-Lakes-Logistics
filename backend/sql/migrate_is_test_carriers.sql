-- Mark the 5 seed/test carriers so they're excluded from production metrics.
ALTER TABLE public.active_carriers
  ADD COLUMN IF NOT EXISTS is_test boolean NOT NULL DEFAULT false;

UPDATE public.active_carriers
SET is_test = true
WHERE id IN (
  '277fbb61-78b2-40b7-9f12-8e8b64ac38d9',  -- Great Lakes Express
  '6d53ff79-b28e-4470-97c2-0f72a2428cce',  -- Motor City Haulers
  '77738853-bf82-4892-a735-1fb96a6ff99c',  -- Belle Isle Reefer
  '1fa0b514-561e-4fc0-8826-2c1c37b3b369',  -- Ambassador Logistics
  'f679cca3-5337-4dda-adfa-349e0f9f8045'   -- Riverfront Freight
);

NOTIFY pgrst, 'reload schema';

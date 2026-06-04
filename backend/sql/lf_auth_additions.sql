-- Light Fleet auth additions
-- Adds PIN-based login to light_vehicle_drivers (mirrors the truck drivers table auth)

ALTER TABLE light_vehicle_drivers ADD COLUMN IF NOT EXISTS pin_hash   text;
ALTER TABLE light_vehicle_drivers ADD COLUMN IF NOT EXISTS phone_e164 text;

CREATE INDEX IF NOT EXISTS idx_lvd_phone       ON light_vehicle_drivers (phone);
CREATE INDEX IF NOT EXISTS idx_lvd_phone_e164  ON light_vehicle_drivers (phone_e164);

-- lf_driver_login: validates phone + PIN, returns driver JSON (mirrors driver_login RPC)
CREATE OR REPLACE FUNCTION lf_driver_login(p_phone text, p_pin text)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  _driver light_vehicle_drivers%ROWTYPE;
  _pin_hash text;
BEGIN
  _pin_hash := encode(sha256(('3ll_driver_pin_salt_v1' || p_pin)::bytea), 'hex');

  SELECT * INTO _driver
  FROM light_vehicle_drivers
  WHERE (phone = p_phone OR phone_e164 = p_phone)
    AND pin_hash = _pin_hash
    AND status != 'inactive'
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  RETURN json_build_object(
    'id',         _driver.id,
    'name',       _driver.name,
    'first_name', split_part(_driver.name, ' ', 1),
    'last_name',  regexp_replace(_driver.name, '^[^ ]+ ?', ''),
    'phone',      coalesce(_driver.phone_e164, _driver.phone),
    'status',     _driver.status
  );
END;
$$;

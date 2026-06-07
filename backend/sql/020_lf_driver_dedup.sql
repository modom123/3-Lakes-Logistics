-- Migration 020: Deduplicate light_vehicle_drivers + add unique constraints
-- Keeps the earliest record per email and per phone, deletes the rest.

-- 1. Remove duplicate rows by email — keep the first (lowest id/earliest created)
DELETE FROM light_vehicle_drivers
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY email
                   ORDER BY created_at ASC NULLS LAST, id ASC
               ) AS rn
        FROM light_vehicle_drivers
        WHERE email IS NOT NULL AND email <> ''
    ) ranked
    WHERE rn > 1
);

-- 2. Remove any remaining duplicates by phone (catches cases with no email)
DELETE FROM light_vehicle_drivers
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY phone
                   ORDER BY created_at ASC NULLS LAST, id ASC
               ) AS rn
        FROM light_vehicle_drivers
        WHERE phone IS NOT NULL AND phone <> ''
    ) ranked
    WHERE rn > 1
);

-- 3. Unique index on email (partial — allows multiple NULL/empty rows)
CREATE UNIQUE INDEX IF NOT EXISTS idx_lvd_email_unique
    ON light_vehicle_drivers (email)
    WHERE email IS NOT NULL AND email <> '';

-- 4. Unique index on phone (partial — allows multiple NULL/empty rows)
CREATE UNIQUE INDEX IF NOT EXISTS idx_lvd_phone_unique
    ON light_vehicle_drivers (phone)
    WHERE phone IS NOT NULL AND phone <> '';

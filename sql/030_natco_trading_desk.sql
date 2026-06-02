-- North America Trading Co — Trading Desk schema additions
-- Idempotent: safe to run multiple times

-- carrier_pay: what we pay the carrier (broker pay - carrier_pay = our spread/profit)
ALTER TABLE loads ADD COLUMN IF NOT EXISTS carrier_pay DECIMAL(10,2);

-- Trade source tag (NATCO trades have load_number starting with NT- and notes containing [NATCO])
-- No schema change needed — reuses existing notes and load_number columns

-- Index for quick NATCO trade lookups
CREATE INDEX IF NOT EXISTS idx_loads_carrier_pay ON loads(carrier_pay);

-- Also add weight_lbs if not present (used in trade form)
ALTER TABLE loads ADD COLUMN IF NOT EXISTS weight_lbs DECIMAL(10,2);

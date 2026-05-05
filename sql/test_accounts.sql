-- ============================================================
-- TEST ACCOUNTS — 3 Lakes Driver App
-- Run in Supabase SQL Editor to create test drivers
-- ============================================================

-- Test Driver 1: Standard driver (all features)
INSERT INTO drivers (
    id,
    name,
    phone,
    phone_e164,
    pin_hash,
    cdl_number,
    cdl_state,
    cdl_expiry,
    status,
    stripe_account_id,
    stripe_account_status,
    fcm_token,
    app_version,
    created_at
) VALUES (
    'aaaaaaaa-0001-4000-a000-000000000001',
    'James Test Driver',
    '555-000-0001',
    '+15550000001',
    -- PIN: 1234  (SHA256 of "1234")
    '03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4',
    'T123456',
    'CA',
    '2027-12-31',
    'active',
    'acct_test_stripe_001',
    'pending',
    'fcm_test_token_driver_001',
    '1.0.0',
    NOW()
) ON CONFLICT (id) DO NOTHING;

-- Test Driver 2: Driver with no Stripe setup (to test onboarding flow)
INSERT INTO drivers (
    id,
    name,
    phone,
    phone_e164,
    pin_hash,
    cdl_number,
    cdl_state,
    cdl_expiry,
    status,
    app_version,
    created_at
) VALUES (
    'aaaaaaaa-0002-4000-a000-000000000002',
    'Maria Test Driver',
    '555-000-0002',
    '+15550000002',
    -- PIN: 5678  (SHA256 of "5678")
    'b7e45d97e7e880766e3c4e0a6076e09e97a5de74a4b20dd67c7c8f42b7b2d6f3',
    'T654321',
    'TX',
    '2026-06-30',
    'active',
    '1.0.0',
    NOW()
) ON CONFLICT (id) DO NOTHING;

-- Test Driver 3: Inactive driver (to test login block)
INSERT INTO drivers (
    id,
    name,
    phone,
    phone_e164,
    pin_hash,
    status,
    created_at
) VALUES (
    'aaaaaaaa-0003-4000-a000-000000000003',
    'Bob Inactive Driver',
    '555-000-0003',
    '+15550000003',
    -- PIN: 0000  (SHA256 of "0000")
    '9af15b336e6a9619928537df30b2e6a2376569fcf9d7e773eccede65606529a0',
    'inactive',
    NOW()
) ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- TEST SESSIONS (pre-login tokens for API testing)
-- ============================================================
INSERT INTO driver_sessions (
    id,
    driver_id,
    token,
    expires_at,
    last_activity_at,
    created_at
) VALUES (
    'bbbbbbbb-0001-4000-b000-000000000001',
    'aaaaaaaa-0001-4000-a000-000000000001',
    'test_token_driver_001_james',
    NOW() + INTERVAL '30 days',
    NOW(),
    NOW()
) ON CONFLICT (id) DO NOTHING;

INSERT INTO driver_sessions (
    id,
    driver_id,
    token,
    expires_at,
    last_activity_at,
    created_at
) VALUES (
    'bbbbbbbb-0002-4000-b000-000000000002',
    'aaaaaaaa-0002-4000-a000-000000000002',
    'test_token_driver_002_maria',
    NOW() + INTERVAL '30 days',
    NOW(),
    NOW()
) ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- TEST LOADS
-- ============================================================
INSERT INTO loads (
    id,
    pickup_address,
    delivery_address,
    broker_phone,
    commodity,
    weight,
    equipment_type,
    rate,
    status,
    driver_id,
    special_instructions,
    created_at
) VALUES
(
    'cccccccc-0001-4000-c000-000000000001',
    '1420 W 35th St, Chicago, IL 60609',
    '4200 Central Ave, Los Angeles, CA 90011',
    '+13125550182',
    'Frozen Beef',
    42000,
    'Reefer',
    1850.00,
    'in_transit',
    'aaaaaaaa-0001-4000-a000-000000000001',
    'Dock door 7. Ask for Mike at pickup.',
    NOW() - INTERVAL '2 hours'
),
(
    'cccccccc-0002-4000-c000-000000000002',
    '3200 Commerce Dr, Dallas, TX 75201',
    '1800 Industrial Blvd, Atlanta, GA 30318',
    '+14695550291',
    'Steel Coils',
    48000,
    'Flatbed',
    2100.00,
    'available',
    NULL,
    'Tarps required. Driver must tarp at origin.',
    NOW() - INTERVAL '1 hour'
),
(
    'cccccccc-0003-4000-c000-000000000003',
    '8900 Airport Blvd, Houston, TX 77061',
    '2400 Airways Blvd, Memphis, TN 38116',
    '+17135550847',
    'Fresh Produce',
    36000,
    'Reefer',
    1875.00,
    'available',
    NULL,
    'Pre-cool to 34°F before loading.',
    NOW() - INTERVAL '30 minutes'
)
ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- TEST MESSAGES
-- ============================================================
INSERT INTO driver_messages (
    id,
    driver_phone,
    direction,
    body,
    msg_type,
    load_id,
    read,
    created_at
) VALUES
(
    'dddddddd-0001-4000-d000-000000000001',
    '+15550000001',
    'inbound',
    'On my way to pickup. ETA 45 min.',
    'general',
    'cccccccc-0001-4000-c000-000000000001',
    true,
    NOW() - INTERVAL '2 hours'
),
(
    'dddddddd-0002-4000-d000-000000000002',
    '+15550000001',
    'outbound',
    'Confirmed. Dock door 7, ask for Mike. Safe travels!',
    'general',
    'cccccccc-0001-4000-c000-000000000001',
    true,
    NOW() - INTERVAL '1 hour 55 minutes'
),
(
    'dddddddd-0003-4000-d000-000000000003',
    '+15550000001',
    'inbound',
    'Loaded up. Heading out now.',
    'general',
    'cccccccc-0001-4000-c000-000000000001',
    false,
    NOW() - INTERVAL '30 minutes'
)
ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- TEST PAYOUT RECORDS
-- ============================================================
INSERT INTO driver_payouts (
    id,
    driver_id,
    load_id,
    gross_cents,
    dispatch_fee_cents,
    insurance_cents,
    net_cents,
    stripe_transfer_id,
    status,
    created_at
) VALUES
(
    'eeeeeeee-0001-4000-e000-000000000001',
    'aaaaaaaa-0001-4000-a000-000000000001',
    'cccccccc-0001-4000-c000-000000000001',
    185000,
    14800,
    4500,
    165700,
    'tr_test_stripe_transfer_001',
    'paid',
    NOW() - INTERVAL '7 days'
)
ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- VERIFY DATA
-- ============================================================
SELECT 'drivers' AS tbl, count(*) FROM drivers WHERE id LIKE 'aaaaaaaa%'
UNION ALL
SELECT 'sessions',        count(*) FROM driver_sessions WHERE id LIKE 'bbbbbbbb%'
UNION ALL
SELECT 'loads',           count(*) FROM loads WHERE id LIKE 'cccccccc%'
UNION ALL
SELECT 'messages',        count(*) FROM driver_messages WHERE id LIKE 'dddddddd%'
UNION ALL
SELECT 'payouts',         count(*) FROM driver_payouts WHERE id LIKE 'eeeeeeee%';

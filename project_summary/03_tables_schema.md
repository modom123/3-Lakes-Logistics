# 03 — Tables & Schema

SQL migrations live in `backend/sql/` (numbered `001`–`007`). RLS is in `007`.

## Core carrier tables
| Table | Purpose | Key columns |
|-------|---------|-------------|
| `active_carriers` | Master carrier record (intake Steps 1 + 6) | `id`, `company_name`, `legal_entity`, `dot_number`, `mc_number`, `ein`, `phone`, `email`, `address`, `years_in_business`, `plan`, `stripe_subscription_id`, `esign_name`, `esign_ip`, `esign_timestamp`, `status`, `created_at` |
| `fleet_assets` | One row per truck/trailer (Step 2) | `id`, `carrier_id` (FK), `truck_id`, `vin`, `year`, `make`, `model`, `trailer_type`, `max_weight`, `equipment_count` |
| `eld_connections` | Step 3 credentials (encrypted) | `id`, `carrier_id`, `eld_provider`, `eld_api_token`, `eld_account_id`, `status`, `last_sync_at` |
| `insurance_compliance` | Step 4 Shield data | `id`, `carrier_id`, `insurance_carrier`, `policy_number`, `policy_expiry`, `coi_url`, `bmc91_ack`, `mcs90_ack`, `safer_consent`, `csa_consent`, `clearinghouse_consent`, `psp_consent`, `last_checked_at` |
| `banking_accounts` | Step 5 Settler payouts | `id`, `carrier_id`, `bank_routing`, `bank_account` (tokenized), `account_type`, `payee_name`, `w9_url`, `verified_at` |
| `signatures_audit` | E-sign evidence chain | `id`, `carrier_id`, `doc_type`, `esign_name`, `ip`, `user_agent`, `pdf_hash`, `ts` |

## Operations tables
| Table | Purpose | Key columns |
|-------|---------|-------------|
| `truck_telemetry` | Live ELD feed | `id`, `carrier_id`, `truck_id`, `eld_provider`, `lat`, `lng`, `speed`, `heading`, `odometer`, `fuel_level`, `engine_hours`, `ts` |
| `driver_hos_status` | Hours-of-service | `id`, `carrier_id`, `driver_id`, `duty_status`, `drive_remaining`, `shift_remaining`, `cycle_remaining`, `ts` |
| `lead_pipeline` | Prospecting pipeline | `id`, `source`, `dot_number`, `mc_number`, `company_name`, `contact`, `phone`, `email`, `score`, `stage`, `owner_agent`, `last_touch_at` |
| `founders_inventory` | Drives the public countdown | `category`, `total`, `claimed`, `reserved` |

## Founders inventory seed
| Category | Total | Claimed |
|---|---|---|
| Dry Van | 300 | 0 |
| Reefer | 200 | 0 |
| Flatbed / Step Deck | 150 | 0 |
| Box Truck 26' (Non-CDL) | 100 | 0 |
| Cargo Van | 100 | 0 |
| Tanker / Hazmat | 50 | 0 |
| Hot Shot | 50 | 0 |
| Auto | 50 | 0 |
| **TOTAL** | **1,000** | **0** |

## RLS (007_rls_policies.sql)
- Service-role bypass for backend writes.
- Carrier-scoped read policies for authed users against their own
  `active_carriers.id`.
- Public read on `founders_inventory` (counters power the public site).

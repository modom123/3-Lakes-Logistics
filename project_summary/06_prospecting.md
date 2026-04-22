# 06 — Prospecting Engines

Modules in `backend/app/prospecting/`. Phase 3 scaffolds (steps 41–60). Each
is wired to `lead_pipeline` and dispatched / audited by the `Scout` agent.

## Sources
| File | Source |
|------|--------|
| `fmcsa_scraper.py` | FMCSA SAFER (DOT / MC by jurisdiction) |
| `gmaps_scraper.py` | Google Maps Places (yards, terminals) |
| `loadboard_scraper.py` | DAT / Truckstop broker + lane signals |
| `truckpaper_scraper.py` | TruckPaper listings (owner-operators) |
| `owner_search.py` | Owner / principal enrichment |

## Scoring & hygiene
| File | Purpose |
|------|---------|
| `scoring.py` | Lead score model |
| `dedupe.py` | Cross-source dedupe (DOT + MC + phone + email) |
| `sms_compliance.py` | TCPA quiet hours, STOP handling, consent ledger |
| `traffic_controller.py` | Rate-limits outbound across channels |

## Outbound
| File | Purpose |
|------|---------|
| `vapi_outbound.py` | AI voice dials via Vapi |
| `email_nurture.py` | Sequenced nurture emails |
| `outbound_schedule.py` | Cadence & retry windows |
| `url_tracking.py` | Click / open attribution |
| `ab_testing.py` | Variant experiments |

## Closed-loop
| File | Purpose |
|------|---------|
| `referral_loop.py` | Carrier → carrier referrals |
| `social_listener.py` | Social mentions / intent signals |
| `airtable_sync.py` | Mirror pipeline into Airtable |
| `dashboard.py` | Conversion funnel counters |
| `daily_digest.py` | Daily ops email / Slack roll-up |
| `dry_run.py` | Test harness — no external side-effects |

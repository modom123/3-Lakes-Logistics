# Production Runbook (Stage 5 step 100)

## Cutover checklist

- [ ] Provision production Supabase project; run `sql/001` → `sql/012`.
- [ ] Generate `PII_ENCRYPTION_KEY` (32 random bytes, base64) and store
      in secret manager. Back up out-of-band.
- [ ] Populate `.env` via secret manager; never commit.
- [ ] Configure Stripe webhook endpoint →
      `https://api.3lakeslogistics.com/api/webhooks/stripe`.
- [ ] Configure Motive webhook →
      `https://api.3lakeslogistics.com/api/webhooks/motive`
      with shared secret in `MOTIVE_WEBHOOK_SECRET`.
- [ ] Configure Vapi webhook with `VAPI_WEBHOOK_SECRET`.
- [ ] Point Twilio inbound SMS to
      `https://api.3lakeslogistics.com/api/webhooks/twilio/sms`.
- [ ] Deploy three service instances (`api`, `worker`, `scheduler`).
      Scheduler must be a **singleton** (one instance only).
- [ ] Verify `/api/health` and `/api/ready` on staging.
- [ ] Run intake → checkout → claim flow on staging with a Stripe test card.
- [ ] Confirm `agent_runs` audit rows appear for dispatched tasks.
- [ ] Enable Sentry DSN.
- [ ] Announce maintenance window; flip DNS.

## Daily ops

- Pulse posts a Slack digest at 07:00 UTC.
- Shield runs FMCSA + COI + Clearinghouse scans at 03:00 / 04:00 / 08:00 UTC.
- Sonny matches loads every 15 minutes.
- Settler issues weekly settlements Friday 18:00 UTC.

## On-call

| Alert                               | First step                                 |
|-------------------------------------|--------------------------------------------|
| Sentry error spike                  | Check `/api/ready`, Supabase dashboard     |
| Webhook signature failures          | Inspect `webhook_log.verified=false`       |
| Queue backlog                       | `select count(*) from agent_tasks where status='pending'`; scale worker |
| Stripe payments failing             | `stripe_events` view + Stripe dashboard    |
| Shield RED carriers                 | Ops Suite → Compliance board               |

## Rollback

Every deploy is a container image. Revert via container tag; DB schema
is forward-compatible (all columns additive).

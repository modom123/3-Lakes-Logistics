# Deploying 3 Lakes Logistics backend to Fly.io

One Fly app (`3lakes-backend`), three process types sharing the same
container image and secret bundle:
- `api` — FastAPI on :8080 (public HTTPS via Fly Proxy)
- `worker` — `python -m app.worker` (no listener)
- `scheduler` — `python -m app.scheduler` (**must stay at 1 machine**)

Static frontends (`index (7).html`, `3LakesLogistics_OpsSuite_v5.html`)
go on Cloudflare Pages or Netlify — see the end of this doc.

---

## 0. Prereqs

```bash
curl -L https://fly.io/install.sh | sh
fly auth login
```

You will also need real accounts / keys for:
Supabase, Stripe, Twilio, Vapi, Motive, FMCSA, Google Maps, Resend (or
Postmark), Sentry, and Slack webhooks.

Generate the PII encryption key **once** and store it safely:
```bash
python -c 'import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'
```

---

## 1. First-time launch

From the `backend/` directory:

```bash
cd backend
fly launch --no-deploy --copy-config --name 3lakes-backend --region ord
```

Answer `n` when Fly asks to create a Postgres / Upstash DB — we use Supabase.

This writes a fly.toml identical to the one already committed. If Fly
overwrites it, `git checkout backend/fly.toml` to restore.

---

## 2. Push secrets (one-shot)

Every value from `.env.example` that is not listed in `fly.toml [env]`
must be a Fly secret. Paste your real values into this block and run it:

```bash
fly secrets set \
  SUPABASE_URL='https://YOUR.supabase.co' \
  SUPABASE_ANON_KEY='...' \
  SUPABASE_SERVICE_ROLE_KEY='...' \
  SUPABASE_JWT_SECRET='...' \
  \
  STRIPE_SECRET_KEY='sk_live_...' \
  STRIPE_WEBHOOK_SECRET='whsec_...' \
  STRIPE_PRICE_FOUNDERS='price_...' \
  STRIPE_PRICE_PRO='price_...' \
  STRIPE_PRICE_SCALE='price_...' \
  \
  TWILIO_ACCOUNT_SID='AC...' \
  TWILIO_AUTH_TOKEN='...' \
  TWILIO_FROM_NUMBER='+1...' \
  \
  VAPI_API_KEY='...' \
  VAPI_WEBHOOK_SECRET='...' \
  VAPI_ASSISTANT_ID_VANCE='...' \
  VAPI_PHONE_NUMBER_ID='...' \
  \
  FMCSA_WEBKEY='...' \
  GOOGLE_MAPS_API_KEY='...' \
  \
  MOTIVE_API_KEY='...' \
  MOTIVE_WEBHOOK_SECRET='...' \
  \
  RESEND_API_KEY='...' \
  POSTMARK_FROM_EMAIL='ops@3lakeslogistics.com' \
  \
  SLACK_WEBHOOK_OPS='https://hooks.slack.com/services/...' \
  SLACK_WEBHOOK_ALERTS='https://hooks.slack.com/services/...' \
  \
  PII_ENCRYPTION_KEY='<value from prereqs>' \
  API_BEARER_TOKEN='<long random string>' \
  SENTRY_DSN='https://...@sentry.io/...'
```

Verify:
```bash
fly secrets list
```

---

## 3. Run the Supabase migrations

Point `psql` at your Supabase project's connection string (Settings →
Database → Connection string → URI) and run every migration in order:

```bash
export SUPA_URL="postgresql://postgres:PASSWORD@db.YOUR.supabase.co:5432/postgres"
for f in sql/0*.sql; do
  echo ">> $f"
  psql "$SUPA_URL" -v ON_ERROR_STOP=1 -f "$f"
done
```

Create the Storage bucket for signed PDFs (Supabase dashboard →
Storage → New bucket → `agreements`, private).

---

## 4. Deploy

```bash
fly deploy
```

Fly builds the image once, rolls it out to all three process types.
Expect ~3-4 min on first deploy, ~60 s on incremental deploys.

Scale each process:
```bash
fly scale count api=2 worker=2 scheduler=1
```

> **Never scale scheduler > 1.** Cron triggers would fire twice and
> double-enqueue every job.

Smoke test:
```bash
fly status
curl https://3lakes-backend.fly.dev/api/health
curl https://3lakes-backend.fly.dev/api/ready
```

---

## 5. Attach your domain

Once DNS is ready, Fly issues TLS automatically:

```bash
fly certs add api.3lakeslogistics.com
# add the CNAME Fly tells you to at your DNS host
fly certs show api.3lakeslogistics.com   # watch until it reads "issued"
```

Update `CORS_ORIGINS` if you host the frontends elsewhere:
```bash
fly secrets set CORS_ORIGINS='https://3lakeslogistics.com,https://ops.3lakeslogistics.com'
```

---

## 6. Register webhook URLs in each vendor dashboard

Every webhook must point at `https://api.3lakeslogistics.com`:

| Vendor  | URL                                                  |
|---------|------------------------------------------------------|
| Stripe  | `.../api/webhooks/stripe`                            |
| Vapi    | `.../api/webhooks/vapi`                              |
| Motive  | `.../api/webhooks/motive`                            |
| Twilio  | `.../api/webhooks/twilio/sms` (Messaging webhook)    |

Confirm each one by pushing a test event from the vendor dashboard then
looking at `webhook_log` in Supabase — every row must have
`verified=true`.

---

## 7. Frontends (Cloudflare Pages)

Both HTML files are static — host them on Cloudflare Pages (free CDN):

```bash
# in repo root
wrangler pages deploy . --project-name 3lakes-public
```

In each HTML file's browser console (or in a tiny inline `<script>`
at the top), set the backend base:

```js
window.__3LL_API_BASE = 'https://api.3lakeslogistics.com';
```

For the Ops Suite, also set the bearer token once per admin browser:
```js
localStorage.setItem('3LL_API_TOKEN', '<API_BEARER_TOKEN>');
```

---

## 8. Day-2 ops

```bash
fly logs                             # tail logs
fly logs -i <machine-id>             # one machine
fly ssh console                      # shell into api machine
fly ssh console -s                   # select process type
fly scale show
fly releases                         # deploy history
fly rollback <version>               # instant rollback
fly status --all                     # every machine's health
```

Scheduler heartbeat — one row per named job in Supabase:
```sql
select name, last_run_at, last_status from scheduled_jobs order by last_run_at desc;
```

Queue depth — if this grows, scale `worker`:
```sql
select agent, count(*) from agent_tasks
where status = 'pending' group by agent;
```

---

## 9. Rollback the full stack

Image rollback:  `fly rollback`
DB schema:  every migration is additive + idempotent, so rolling back
code is always safe. Dropping columns requires a manual migration.

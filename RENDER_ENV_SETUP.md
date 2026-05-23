# Render Environment Variables Setup

Go to **Render → Your Service → Environment** and add each of these.

## REQUIRED (app won't start without these)

| Variable | Where to get it |
|----------|----------------|
| `SUPABASE_URL` | Supabase dashboard → Project Settings → API |
| `SUPABASE_ANON_KEY` | Supabase dashboard → Project Settings → API |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase dashboard → Project Settings → API (service_role) |
| `API_BEARER_TOKEN` | Make up a strong secret — Eagle Eye uses this to talk to the backend. Same value goes in Vercel as `VITE_API_BEARER_TOKEN`. |
| `ENV` | `production` |

## AI — Anthropic + OpenRouter

| Variable | Where to get it |
|----------|----------------|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com → API Keys |
| `OPENROUTER_API_KEY` | https://openrouter.ai → Keys |
| `OPENROUTER_MODEL` | `qwen/qwen-2.5-72b-instruct` (default — change to upgrade) |

## EXTERNAL BOND — Daytona + Bond Channel

| Variable | Value |
|----------|-------|
| `DAYTONA_SANDBOX_ID` | `2a50d3c2-f813-49c0-8dec-f9248581c5c6` |
| `BOND_API_KEY` | Make up a strong secret — External Bond passes this in `X-Bond-Key` header |

## OUTBOUND CALLS — Bland AI

| Variable | Where to get it |
|----------|----------------|
| `BLAND_AI_API_KEY` | https://app.bland.ai → API Keys (must differ from Org ID) |
| `BLAND_AI_ORG_ID` | https://app.bland.ai → Account Settings → Org ID |
| `BLAND_AI_WEBHOOK_SECRET` | https://app.bland.ai → Webhooks → Signing secret |

**Also do in Bland dashboard:**
1. Account Settings → IP Allowlist → toggle **OFF** (or add Render IP)
2. Verify API key ≠ Org ID — regenerate if identical

## SMS — Twilio

| Variable | Where to get it |
|----------|----------------|
| `TWILIO_ACCOUNT_SID` | Twilio console → Account Info |
| `TWILIO_AUTH_TOKEN` | Twilio console → Account Info |
| `TWILIO_FROM_NUMBER` | `+13135469006` |

## PAYMENTS — Stripe

| Variable | Where to get it |
|----------|----------------|
| `STRIPE_SECRET_KEY` | Stripe dashboard → Developers → API Keys → Secret key |
| `STRIPE_WEBHOOK_SECRET` | Stripe dashboard → Webhooks → Signing secret |
| `STRIPE_PRICE_FOUNDERS` | Stripe dashboard → Products → Founders plan → Price ID |

## EMAIL INGEST — SendGrid

| Variable | Where to get it |
|----------|----------------|
| `SENDGRID_API_KEY` | https://app.sendgrid.com → Settings → API Keys |

**Also do (DNS + SendGrid dashboard):**
1. Add DNS MX record: Host `loads.3lakeslogistics.com` → `mx.sendgrid.net` (priority 10)
2. SendGrid → Settings → Inbound Parse → Add Host
   - Hostname: `loads.3lakeslogistics.com`
   - URL: `https://YOUR-RENDER-URL/api/webhooks/email/inbound`
   - Check "POST the raw, full MIME message"
3. Allow 24–48 hours for DNS to propagate

## EMAIL DELIVERY — Postmark

| Variable | Where to get it |
|----------|----------------|
| `POSTMARK_SERVER_TOKEN` | https://account.postmarkapp.com → Servers → API Tokens |

## E-SIGNATURE — Adobe Sign

| Variable | Where to get it |
|----------|----------------|
| `ADOBE_CLIENT_ID` | Adobe Developer Console → Your App → Credentials |
| `ADOBE_CLIENT_SECRET` | Adobe Developer Console → Your App → Credentials |
| `ADOBE_ACCOUNT_ID` | Adobe Sign dashboard → Account Settings |

## OPTIONAL

| Variable | Notes |
|----------|-------|
| `REDIS_URL` | Redis Cloud — enables caching |
| `SENTRY_DSN` | Sentry.io — error tracking |
| `FMCSA_WEBKEY` | FMCSA SAFER web services — carrier safety lookups |
| `GOOGLE_MAPS_API_KEY` | Fleet tracking map |

---

## Minimum viable set — copy into Render dashboard

```
ENV=production
SUPABASE_URL=https://zngipootstubwvgdmckt.supabase.co
SUPABASE_ANON_KEY=<from supabase>
SUPABASE_SERVICE_ROLE_KEY=<from supabase>
API_BEARER_TOKEN=<your-secret-token>
ANTHROPIC_API_KEY=<from anthropic>
OPENROUTER_API_KEY=<from openrouter>
OPENROUTER_MODEL=qwen/qwen-2.5-72b-instruct
DAYTONA_SANDBOX_ID=2a50d3c2-f813-49c0-8dec-f9248581c5c6
BOND_API_KEY=<your-secret-token>
BLAND_AI_API_KEY=<from bland>
BLAND_AI_ORG_ID=<from bland>
TWILIO_ACCOUNT_SID=<from twilio>
TWILIO_AUTH_TOKEN=<from twilio>
TWILIO_FROM_NUMBER=+13135469006
STRIPE_SECRET_KEY=<from stripe>
STRIPE_WEBHOOK_SECRET=<from stripe>
POSTMARK_SERVER_TOKEN=<from postmark>
SENDGRID_API_KEY=<from sendgrid>
```

---

## Verify Render is live

```
https://YOUR-RENDER-URL/api/health/ping
```
Should return: `"ok"`

Full health check:
```
https://YOUR-RENDER-URL/api/health/full
```

## Deployment

Render auto-deploys on every push to `main` (configured in `render.yaml`).
The Dockerfile at repo root builds the FastAPI backend — Render detects it automatically.

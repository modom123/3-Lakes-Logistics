# Railway Environment Variables Setup

Go to **Railway → Your Project → Variables** and add each of these.

## REQUIRED (app won't work without these)

| Variable | Where to get it |
|----------|----------------|
| `SUPABASE_URL` | Supabase dashboard → Project Settings → API |
| `SUPABASE_ANON_KEY` | Supabase dashboard → Project Settings → API |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase dashboard → Project Settings → API (service_role) |
| `API_BEARER_TOKEN` | Make up a strong secret — this is what Eagle Eye uses to talk to the backend. Same value goes in Vercel as `API_BEARER_TOKEN`. |
| `ENV` | `production` |

## REQUIRED FOR VERCEL (set these in Vercel too)

| Variable | Value |
|----------|-------|
| `API_BASE_URL` | Your Railway public URL, e.g. `https://3lakes-api-primary.up.railway.app` |
| `API_BEARER_TOKEN` | Same value as Railway |

## PAYMENTS — Stripe

| Variable | Where to get it |
|----------|----------------|
| `STRIPE_SECRET_KEY` | Stripe dashboard → Developers → API Keys → Secret key |
| `STRIPE_WEBHOOK_SECRET` | Stripe dashboard → Webhooks → Signing secret |
| `STRIPE_PRICE_FOUNDERS` | Stripe dashboard → Products → Founders plan → Price ID |

## SMS — Twilio

| Variable | Where to get it |
|----------|----------------|
| `TWILIO_ACCOUNT_SID` | Twilio console → Account Info |
| `TWILIO_AUTH_TOKEN` | Twilio console → Account Info |
| `TWILIO_FROM_NUMBER` | `+13135469006` (already configured) |

## OUTBOUND CALLS — Bland AI (Issue #3 fix)

| Variable | Where to get it |
|----------|----------------|
| `BLAND_AI_API_KEY` | https://app.bland.ai → API Keys (must be DIFFERENT from Org ID) |
| `BLAND_AI_ORG_ID` | https://app.bland.ai → Account Settings → Org ID |
| `BLAND_AI_WEBHOOK_SECRET` | https://app.bland.ai → Webhooks → Signing secret |

**ALSO DO THIS IN BLAND DASHBOARD:**
1. Go to https://app.bland.ai → Account Settings → IP Allowlist
2. Toggle IP Allowlist **OFF** (or add your Railway server IP)
3. Verify your API key ≠ Org ID — if identical, regenerate the API key

## EMAIL INGEST — SendGrid (Issue #4 fix)

| Variable | Where to get it |
|----------|----------------|
| `SENDGRID_API_KEY` | https://app.sendgrid.com → Settings → API Keys |
| `SENDGRID_INBOUND_EMAIL` | `loads@3lakeslogistics.com` (already set) |
| `SENDGRID_INBOUND_SECRET` | Optional — from SendGrid Inbound Parse webhook |

**ALSO DO THIS (DNS + SendGrid dashboard):**
1. Add DNS MX record via your domain registrar:
   - Host: `loads.3lakeslogistics.com`
   - Type: MX
   - Priority: 10
   - Value: `mx.sendgrid.net`
2. Go to https://app.sendgrid.com → Settings → Inbound Parse → Add Host
   - Hostname: `loads.3lakeslogistics.com`
   - URL: `https://YOUR-RAILWAY-URL/api/webhooks/email/inbound`
   - Check "POST the raw, full MIME message"
3. Wait 24-48 hours for DNS to propagate

## AI — Anthropic (Claude agents)

| Variable | Where to get it |
|----------|----------------|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com → API Keys |

## E-SIGNATURE — Adobe Sign

| Variable | Where to get it |
|----------|----------------|
| `ADOBE_CLIENT_ID` | Adobe Developer Console → Your App → Credentials |
| `ADOBE_CLIENT_SECRET` | Adobe Developer Console → Your App → Credentials |
| `ADOBE_ACCOUNT_ID` | Adobe Sign dashboard → Account Settings |

## EMAIL DELIVERY — Postmark

| Variable | Where to get it |
|----------|----------------|
| `POSTMARK_SERVER_TOKEN` | https://account.postmarkapp.com → Servers → API Tokens |

## OPTIONAL (nice to have at launch)

| Variable | Notes |
|----------|-------|
| `REDIS_URL` | Redis Cloud or Railway Redis add-on — enables caching |
| `SENTRY_DSN` | Sentry.io — error tracking |
| `FMCSA_WEBKEY` | FMCSA SAFER web services — carrier safety lookups |
| `GOOGLE_MAPS_API_KEY` | Fleet tracking map |

---

## Quick Copy — Minimum viable set to get backend running

```
ENV=production
SUPABASE_URL=https://zngipootstubwvgdmckt.supabase.co
SUPABASE_ANON_KEY=<from supabase>
SUPABASE_SERVICE_ROLE_KEY=<from supabase>
API_BEARER_TOKEN=<your-secret-token>
STRIPE_SECRET_KEY=<from stripe>
STRIPE_WEBHOOK_SECRET=<from stripe>
TWILIO_ACCOUNT_SID=<from twilio>
TWILIO_AUTH_TOKEN=<from twilio>
TWILIO_FROM_NUMBER=+13135469006
BLAND_AI_API_KEY=<from bland>
BLAND_AI_ORG_ID=<from bland>
ANTHROPIC_API_KEY=<from anthropic>
POSTMARK_SERVER_TOKEN=<from postmark>
SENDGRID_API_KEY=<from sendgrid>
```

---

## How to verify Railway is live

Once you've added vars and deployed, visit:
```
https://YOUR-RAILWAY-URL/api/health/ping
```
Should return: `"ok"`

Full health check (all integrations):
```
https://YOUR-RAILWAY-URL/api/health/full
```

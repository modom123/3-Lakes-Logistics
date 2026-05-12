# Get All 10 Credentials for Vance Launch

## Status: 2/3 Supabase Done ✅

You've provided:
- ✅ `SUPABASE_ANON_KEY` = (publishable key provided)
- ✅ `SUPABASE_SERVICE_ROLE_KEY` = (secret key provided)
- ⏳ `SUPABASE_URL` = Need this from dashboard (Settings → API)

---

## Get the Remaining 7 Keys

### 1️⃣ **Bland AI** (Make prospecting calls)

1. Visit: https://bland.ai/
2. Sign in → Dashboard → Settings → API Keys
3. Copy your **API Key** (looks like: `bland_xxx...`)
4. Also need: **Webhook Secret** from Webhooks section

**Credentials:**
```
BLAND_AI_API_KEY=your_api_key_here
BLAND_AI_WEBHOOK_SECRET=your_webhook_secret_here
```

---

### 2️⃣ **Anthropic Claude** (Vance's brain)

1. Visit: https://console.anthropic.com/
2. Sign in → API Keys
3. Create new API key or copy existing
4. Copy the key (starts with `sk-ant-`)

**Credential:**
```
ANTHROPIC_API_KEY=sk-ant-your_key_here
```

---

### 3️⃣ **Postmark** (Send follow-up emails)

1. Visit: https://postmarkapp.com/
2. Sign in → Servers → 3 Lakes Logistics (or create)
3. Settings → API Tokens
4. Copy **Server Token** (looks like: `xxxxxxxx-xxxx-xxxx...`)

**Credential:**
```
POSTMARK_SERVER_TOKEN=your_server_token_here
```

---

### 4️⃣ **Twilio** (Send SMS reminders)

1. Visit: https://www.twilio.com/
2. Sign in → Dashboard
3. Copy **Account SID** (looks like: `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
4. Copy **Auth Token** (long string)
5. Buy a phone number or use existing: **Phone Number** (looks like: `+18005551234`)

**Credentials:**
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_FROM_NUMBER=+18005551234
```

---

## Summary: What to Provide

Reply with these 10 values in this format:

```
SUPABASE_URL=https://...
SUPABASE_ANON_KEY=sb_publishable_...
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...

BLAND_AI_API_KEY=...
BLAND_AI_WEBHOOK_SECRET=...

ANTHROPIC_API_KEY=sk-ant-...

POSTMARK_SERVER_TOKEN=...

TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...
```

Once you provide all 10, I'll:
1. Create your `.env` file
2. Test the configuration
3. You'll be ready to launch Vance ✅

---

## Time Estimate

- Supabase URL: 1 minute ⏳
- Bland AI: 5 minutes
- Anthropic: 3 minutes
- Postmark: 5 minutes
- Twilio: 5 minutes

**Total: ~20 minutes to have everything ready**

---

## Which ones do you already have?

Do you have accounts at:
- [ ] Bland AI?
- [ ] Anthropic?
- [ ] Postmark?
- [ ] Twilio?

If not, I can guide you through setting them up (they're all free tier to start).

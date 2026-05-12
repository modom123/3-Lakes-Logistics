# API Credentials & Integration Audit

## 🚨 CRITICAL — Must Have to Launch

These APIs are **actively used** in the code. Without them, Vance won't work.

### 1. **Supabase** (Database)
- **Status:** ⚠️ CRITICAL
- **Used For:** Fleet data, leads, messages, compliance records
- **Credentials Needed:**
  ```
  SUPABASE_URL=https://your-project.supabase.co
  SUPABASE_ANON_KEY=eyJhbGc...
  SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...
  ```
- **Where to Get:**
  1. Visit: https://supabase.com/
  2. Create/log into project
  3. Settings → API → Copy keys
- **Files Using:** `backend/app/db/` (all database queries)

### 2. **Bland AI** (Outbound Prospecting Calls)
- **Status:** ✅ CODE READY
- **Used For:** Vance makes calls to prospects ($0.06/min base)
- **Credentials Needed:**
  ```
  BLAND_AI_API_KEY=your_api_key
  BLAND_AI_WEBHOOK_SECRET=your_webhook_secret
  ```
- **Where to Get:**
  1. Visit: https://bland.ai/
  2. Sign up, go to Dashboard → Settings → API Keys
  3. Copy API key
  4. Create webhook URL in Bland dashboard: `https://your-api.com/api/webhooks/bland`
  5. Copy webhook secret
- **Files Using:** 
  - `backend/app/agents/bland_client.py` (initiates calls)
  - `backend/app/api/routes_bland_webhooks.py` (receives events)

### 3. **Postmark** (Email)
- **Status:** ✅ CODE READY
- **Used For:** Send follow-up emails with demo video + Calendly link
- **Credentials Needed:**
  ```
  POSTMARK_SERVER_TOKEN=your_server_token
  POSTMARK_FROM_EMAIL=ops@3lakeslogistics.com
  ```
- **Where to Get:**
  1. Visit: https://postmarkapp.com/
  2. Create account, add server "3 Lakes Logistics"
  3. Settings → Servers → Copy Server Token
  4. Verify sender email domain
- **Cost:** $10/month for 25K emails, $0.0004/email
- **Files Using:** `backend/app/prospecting/follow_up.py` (send_follow_up_email)

### 4. **Twilio** (SMS)
- **Status:** ✅ CODE READY
- **Used For:** Send 24h SMS reminder if prospect doesn't book
- **Credentials Needed:**
  ```
  TWILIO_ACCOUNT_SID=AC123...
  TWILIO_AUTH_TOKEN=abc123...
  TWILIO_FROM_NUMBER=+18005551234
  ```
- **Where to Get:**
  1. Visit: https://www.twilio.com/
  2. Create account, buy phone number
  3. Dashboard → Copy Account SID + Auth Token
  4. Phone Numbers → Copy your number
- **Cost:** ~$0.0075/SMS, $1/month phone number
- **Files Using:** `backend/app/prospecting/follow_up.py` (send_sms_reminder)

### 5. **Anthropic Claude** (AI Agent Brain)
- **Status:** ✅ USED IN BLAND AI
- **Used For:** Powers Vance's conversation intelligence
- **Credentials Needed:**
  ```
  ANTHROPIC_API_KEY=sk-ant-...
  ```
- **Where to Get:**
  1. Visit: https://console.anthropic.com/
  2. Create account/API key
  3. Copy API key
- **Cost:** ~$0.10 per prospecting call (Vance uses Claude Opus)
- **Files Using:** `backend/app/agents/bland_client.py` (VANCE_SYSTEM_PROMPT)

---

## 🟡 HIGH PRIORITY — Driver App & Operations

These are used but not blocking Vance from working.

### 6. **Google Maps API**
- **Status:** ⚠️ RECOMMENDED
- **Used For:** Driver app navigation (pickup/delivery addresses)
- **Credentials Needed:**
  ```
  GOOGLE_MAPS_API_KEY=AIzaSy...
  ```
- **Where to Get:**
  1. Google Cloud Console
  2. Create project, enable Maps API
  3. Create API key
- **Cost:** Free tier covers ~25K requests/month
- **Files Using:** `driver-pwa/index-v2.html` (Google Maps links)

### 7. **Stripe** (Payments - Optional for Founders Billing)
- **Status:** ⚠️ NOT YET USED
- **Used For:** Charge drivers $300/month for Founders program
- **Credentials Needed:**
  ```
  STRIPE_SECRET_KEY=sk_live_...
  STRIPE_WEBHOOK_SECRET=whsec_...
  STRIPE_PRICE_FOUNDERS=price_...
  ```
- **Where to Get:** https://stripe.com/
- **Files Using:** `backend/app/billing/` (not yet built)
- **Priority:** Can defer until ready to charge drivers

---

## 🟢 OPTIONAL — Not Used Yet

These are defined but NOT currently implemented. You can skip them for MVP.

### 8. **Vapi** (Alternative Voice Provider)
- **Status:** ❌ REPLACED BY BLAND AI
- **Why:** Bland AI is cheaper ($0.06/min vs $0.20+/min)
- **Leave blank:** `VAPI_API_KEY`, `VAPI_ASSISTANT_ID_VANCE`, `VAPI_PHONE_NUMBER_ID`

### 9. **ElevenLabs** (Text-to-Speech)
- **Status:** ❌ NOT USED
- **Why:** Bland AI has built-in audio
- **Leave blank:** `ELEVENLABS_API_KEY`

### 10. **SendGrid** (Email Ingest)
- **Status:** ⏳ FUTURE
- **Used For:** Parse inbound emails for load board integration
- **Leave blank:** `SENDGRID_API_KEY`, `SENDGRID_INBOUND_SECRET`

### 11. **Load Board APIs** (Load Sourcing - Sonny Agent)
- **Status:** ⏳ FUTURE (Phase 2)
- **Used For:** Auto-pull loads from 15+ load boards
- **Leave blank:** All DAT, TruckStop, Uber Freight, etc.

### 12. **Telematics Integrations** (Motive, Samsara, etc.)
- **Status:** ⏳ FUTURE (Phase 3)
- **Used For:** Real-time GPS, HOS, maintenance data
- **Leave blank:** `MOTIVE_API_KEY`, `SAMSARA_API_KEY`, etc.

### 13. **Sentry** (Error Tracking)
- **Status:** 🟡 OPTIONAL
- **Used For:** Monitor production errors
- **Leave blank:** `SENTRY_DSN` (for now)

---

## ✅ Your Checklist: Minimum to Launch Vance

To launch prospecting RIGHT NOW, you need only these 5:

- [ ] **SUPABASE_URL** — Database location
- [ ] **SUPABASE_ANON_KEY** — Database read access
- [ ] **SUPABASE_SERVICE_ROLE_KEY** — Database write access
- [ ] **BLAND_AI_API_KEY** — Make calls ($0.06/min)
- [ ] **BLAND_AI_WEBHOOK_SECRET** — Receive call events
- [ ] **POSTMARK_SERVER_TOKEN** — Send follow-up emails
- [ ] **TWILIO_ACCOUNT_SID** — Send SMS reminders
- [ ] **TWILIO_AUTH_TOKEN** — SMS auth
- [ ] **TWILIO_FROM_NUMBER** — SMS from number
- [ ] **ANTHROPIC_API_KEY** — Claude for Vance brain

**That's 10 credentials for full Vance pipeline.**

---

## 📋 .env Template

Copy this into your `.env` file and fill in the blanks:

```bash
# ========== CRITICAL FOR VANCE ==========
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

BLAND_AI_API_KEY=your_bland_ai_key
BLAND_AI_WEBHOOK_SECRET=your_webhook_secret

POSTMARK_SERVER_TOKEN=your_postmark_token
POSTMARK_FROM_EMAIL=ops@3lakeslogistics.com

TWILIO_ACCOUNT_SID=AC123abc456def
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=+18005551234

ANTHROPIC_API_KEY=sk-ant-your_key_here

# ========== RECOMMENDED ==========
GOOGLE_MAPS_API_KEY=AIzaSy_your_key_here

# ========== FUTURE (LEAVE BLANK FOR NOW) ==========
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_FOUNDERS=

VAPI_API_KEY=
VAPI_ASSISTANT_ID_VANCE=
VAPI_PHONE_NUMBER_ID=

ELEVENLABS_API_KEY=

MOTIVE_API_KEY=
SAMSARA_API_KEY=
GEOTAB_USERNAME=
GEOTAB_PASSWORD=
OMNITRACS_API_KEY=

SENDGRID_API_KEY=
SENDGRID_INBOUND_SECRET=
SENDGRID_INBOUND_EMAIL=loads@3lakes.logistics

# Load Board APIs (Sonny - Phase 2)
DAT_CLIENT_ID=
DAT_CLIENT_SECRET=
TRUCKSTOP_USERNAME=
TRUCKSTOP_PASSWORD=
TRUCKSTOP_PARTNER_ID=
LOADBOARD_123_API_KEY=
TRUCKERPATH_API_KEY=
DIRECT_FREIGHT_USERNAME=
DIRECT_FREIGHT_PASSWORD=
UBER_FREIGHT_CLIENT_ID=
UBER_FREIGHT_CLIENT_SECRET=
LOADSMART_API_KEY=
NEWTRUL_API_KEY=
FLOCK_FREIGHT_API_KEY=
JBHUNT_CLIENT_ID=
JBHUNT_CLIENT_SECRET=
COYOTE_CLIENT_ID=
COYOTE_CLIENT_SECRET=
ARRIVE_CLIENT_ID=
ARRIVE_CLIENT_SECRET=
ECHO_GLOBAL_API_KEY=
CARGO_CHIEF_API_KEY=

FMCSA_WEBKEY=

AIRTABLE_API_KEY=
AIRTABLE_BASE_ID=

SENTRY_DSN=

REDIS_URL=
BACKUP_API_URL=

API_BEARER_TOKEN=change-me-in-prod
```

---

## 🚀 Priority Order to Get Keys

**TODAY (for launching Vance):**
1. Supabase - 5 minutes
2. Bland AI - 10 minutes
3. Postmark - 5 minutes
4. Twilio - 10 minutes
5. Anthropic - 5 minutes

**TOTAL TIME: ~35 minutes to be fully operational**

**LATER (when you scale):**
- Google Maps (driver app)
- Stripe (billing)
- Load board APIs (Sonny agent)

---

## Questions?

**"Do I already have these?"**
- Check your `.env` file (not in repo for security)
- Check your account settings at each service

**"Which ones do I need RIGHT NOW?"**
- Just the 5 marked CRITICAL above
- Rest are optional/future

**"What if I don't have Anthropic key?"**
- Vance won't work (he needs Claude)
- Get one free at https://console.anthropic.com/

**"Can I test without these?"**
- Yes! Mock mode exists in code for testing
- But real calls need real credentials

---

## Files Reference

- **Settings definitions:** `backend/app/settings.py`
- **Bland AI client:** `backend/app/agents/bland_client.py`
- **Email/SMS setup:** `backend/app/prospecting/follow_up.py`
- **Webhook handler:** `backend/app/api/routes_bland_webhooks.py`

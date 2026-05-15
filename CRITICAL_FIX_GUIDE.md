# CRITICAL FIX GUIDE — Phase 9 Database + Bland AI + SendGrid

**Status**: 3 blocking issues preventing production deployment
**Timeline**: 1-2 hours to complete all three

---

## 🔴 ISSUE #1: Deploy Database Schema for Driver App (Phase 9)

### What's Missing
The driver mobile app (PWA) requires these database tables to function:
- `driver_messages` — SMS threads
- `driver_sessions` — Authentication tokens
- `driver_payouts` — Stripe Connect payouts

Plus missing columns on `drivers` and `loads` tables.

### How to Fix

#### Option A: Deploy via Supabase Dashboard (Recommended for 1st time)
1. Go to https://supabase.com → Login to your project
2. Go to **SQL Editor** → Click **New Query**
3. Copy-paste contents of: `sql/driver_schema_additions.sql`
4. Click **Run** button (▶️)
5. Verify all statements executed without errors (should see ✅ checks)

#### Option B: Deploy via CLI (if you have supabase CLI installed)
```bash
cd /home/user/3-Lakes-Logistics
supabase db push --dry-run  # Preview changes
supabase db push            # Deploy
```

#### Option C: Deploy via Python migration tool
```bash
cd /home/user/3-Lakes-Logistics/backend
python -m pip install supabase
python -c "
from supabase import create_client
import os

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
client = create_client(url, key)

with open('../sql/driver_schema_additions.sql') as f:
    schema = f.read()
    # Execute manually in Supabase dashboard (recommended)
    print('Execute this in Supabase SQL Editor:')
    print(schema)
"
```

### Verification Checklist
After deployment, verify in Supabase dashboard:

```sql
-- Run each query in SQL Editor to verify tables exist

-- Check 1: driver_messages table
SELECT COUNT(*) FROM driver_messages;

-- Check 2: driver_sessions table
SELECT COUNT(*) FROM driver_sessions;

-- Check 3: driver_payouts table
SELECT COUNT(*) FROM driver_payouts;

-- Check 4: New columns on drivers table
SELECT pin_hash, stripe_account_id, fcm_token, phone_e164, last_location FROM drivers LIMIT 1;

-- Check 5: New columns on loads table
SELECT pickup_address, delivery_address, broker_phone, delivered_at, driver_id FROM loads LIMIT 1;

-- Check 6: All indexes created
SELECT indexname FROM pg_indexes WHERE tablename IN ('driver_messages', 'driver_sessions', 'driver_payouts', 'drivers', 'loads')
ORDER BY tablename, indexname;
```

All queries should return results without errors. ✅ = Ready to proceed to Issue #2.

---

## 🔴 ISSUE #2: Fix Bland AI IP Allowlist (blocks Vance Dialer calls)

### What's Blocking
The Vance Dialer (call bot in EAGLE EYE) fails with: **"Host not in allowlist"**
- Root cause: Bland AI account has IP allowlist enabled
- Impact: Manual calls and auto-calling don't work in production

### How to Fix

#### Step 1: Access Bland AI Dashboard
1. Go to https://app.bland.ai
2. Login with your Bland AI account
3. Navigate to **Account Settings** (click user icon → Settings)

#### Step 2: Disable or Whitelist IP
You have two options:

**OPTION A: Disable IP Allowlist (Easiest for dev/staging)**
1. In Settings, find **IP Allowlist** or **API Security**
2. Toggle to **OFF** or click **Disable**
3. Confirm the change
4. Test immediately: Go to EAGLE EYE → Agents page → Try "Call Now"

**OPTION B: Whitelist Production Server IP (More Secure)**
1. Find your production server's public IP:
   ```bash
   # If on Cloud Run, Railway, Heroku, etc.
   # Check your deployment dashboard for outbound IP
   ```
2. In Bland AI Settings, go to **IP Allowlist**
3. Click **Add IP** → Enter your server's public IP
4. Click **Save**
5. Test the call

#### Step 3: Verify API Keys (Critical)
⚠️ **IMPORTANT**: Check that your API key is correct in `.env`:

In Bland AI dashboard:
1. Go to **API Keys** section
2. Copy your **API Key** (should start with `bld_` or similar)
3. Verify it's NOT the same as your **Organization ID**

Update your backend `.env`:
```bash
BLAND_AI_API_KEY=<your_api_key_from_dashboard>
BLAND_AI_ORG_ID=org_<your_org_id>
BLAND_AI_WEBHOOK_SECRET=whsec_<your_webhook_secret>
```

### Testing
1. Deploy backend with updated `.env`
2. Go to **EAGLE EYE** → **Agents** page
3. Enter: Name="Test", Phone="+1 (555) 123-4567", Notes="Test call"
4. Click **Call Now**
5. Should see: ✅ "Call started successfully" with Call ID
6. Check **Recent Calls** table for the entry
7. Check **agent_log** table in Supabase for `vance` agent entry

---

## 🔴 ISSUE #3: Configure SendGrid Email Ingest (for Document Vault)

### What's Blocking
Email attachments sent to `loads@3lakeslogistics.com` don't auto-upload to Document Vault.
- Root cause: SendGrid webhook not configured
- Impact: Invoices, BOLs, contracts don't auto-sync from email

### How to Fix

#### Step 1: Update DNS Records (takes 24-48 hours)
You need to set up email routing for `loads@3lakeslogistics.com`

**Option A: Using SendGrid's Sender Authentication (Recommended)**
1. Go to https://sendgrid.com → Login
2. Go to **Settings** → **Sender Authentication** → **Authenticate Your Domain**
3. Add domain: `3lakeslogistics.com`
4. Follow the wizard to add DNS records (MX, SPF, DKIM)
5. Once verified (status shows ✅), proceed to Step 2

**Option B: Update DNS at Your Domain Registrar**
If you manage DNS directly:
1. Add **MX Record**:
   - Host: `loads.3lakeslogistics.com`
   - Value: `mx.sendgrid.net`
   - Priority: `10`

2. Wait 24-48 hours for DNS to propagate
3. Test propagation:
   ```bash
   nslookup -type=MX loads.3lakeslogistics.com
   # Should return: mx.sendgrid.net
   ```

#### Step 2: Configure SendGrid Inbound Parse Webhook
1. Go to https://app.sendgrid.com → **Settings** → **Inbound Parse**
2. Click **Create New Inbound Parse Webhook**
3. Fill in:
   - **Hostname**: `loads.3lakeslogistics.com`
   - **URL**: `https://YOUR_BACKEND_DOMAIN/api/webhooks/email/inbound`
   - **POST the raw, full MIME message**: ✅ (checked)
   - **Spam Check**: ✅ (optional, checked)
4. Click **Test Your Webhook** (should see 200 OK)
5. Click **Save**

#### Step 3: Update Backend Environment Variables
In your production `.env`:
```bash
# SendGrid email ingest
SENDGRID_API_KEY=SG.xxxxxxxxxxxx_your_api_key
SENDGRID_INBOUND_EMAIL=loads@3lakeslogistics.com
SENDGRID_INBOUND_SECRET=<optional_verification_key>
```

#### Step 4: Deploy Backend
Redeploy with updated environment variables:
```bash
# If on Cloud Run
gcloud run deploy backend --set-env-vars SENDGRID_API_KEY=...

# If on Railway
railway deploy

# If on Heroku
heroku config:set SENDGRID_API_KEY=...
```

### Testing
1. Send test email to `loads@3lakeslogistics.com` with PDF attachment
2. Wait 5-10 seconds
3. Check **Document Vault** in EAGLE EYE:
   - New document should appear with status "pending"
   - Should extract file type (PDF, JPEG, etc.)
4. Check backend logs:
   ```bash
   # Should see: "Received inbound email with attachment"
   # Followed by: "Saved to document_vault"
   ```
5. After 30-60 seconds, status should change to "complete"

---

## ✅ Post-Fix Validation Checklist

### Issue #1 (Database)
- [ ] All 3 tables exist in Supabase: `driver_messages`, `driver_sessions`, `driver_payouts`
- [ ] Drivers table has: `pin_hash`, `stripe_account_id`, `fcm_token`, `phone_e164`, `last_location`
- [ ] Loads table has: `pickup_address`, `delivery_address`, `driver_id`, `delivered_at`
- [ ] All indexes created successfully
- [ ] RLS policies enabled on sensitive tables

### Issue #2 (Bland AI)
- [ ] IP allowlist disabled OR production IP whitelisted
- [ ] API key verified (different from Org ID)
- [ ] Test call from EAGLE EYE succeeds
- [ ] Call appears in agent_log table
- [ ] Recent calls table populates

### Issue #3 (SendGrid)
- [ ] DNS MX record for `loads.3lakeslogistics.com` resolves
- [ ] SendGrid webhook configured and tested (200 OK)
- [ ] Test email with attachment received
- [ ] Document appears in Document Vault (pending → complete)
- [ ] Backend logs show email ingest success

---

## 🆘 Troubleshooting

### Database Issues
```
Error: "relation driver_messages does not exist"
→ Run driver_schema_additions.sql again
→ Check Supabase SQL Editor for errors

Error: "permission denied"
→ Use SUPABASE_SERVICE_ROLE_KEY (not anon key)
→ If using CLI: supabase --token $SUPABASE_ACCESS_TOKEN
```

### Bland AI Issues
```
Error: "Host not in allowlist"
→ Go to Bland dashboard → Settings → Disable IP Allowlist
→ OR add your server's public IP to whitelist
→ Verify API key is not identical to Org ID

Error: "Calls don't appear in Recent Calls"
→ Check agent_log table: SELECT * FROM agent_log WHERE agent='vance' ORDER BY created_at DESC LIMIT 10;
→ Check backend logs for routes_prospecting.py errors
→ Verify require_bearer token in request headers
```

### SendGrid Issues
```
Error: "MX record not found"
→ DNS propagation can take 24-48 hours
→ Test with: nslookup -type=MX loads.3lakeslogistics.com
→ Or use online tool: https://www.mxtoolbox.com/

Error: "Webhook failed with 401"
→ Verify webhook URL is accessible from internet
→ Test with: curl -X POST https://your-api.com/api/webhooks/email/inbound
→ Check SENDGRID_INBOUND_EMAIL env var matches configured hostname

Error: "Email received but not in Document Vault"
→ Check backend logs for email_ingest.py errors
→ Verify SENDGRID_INBOUND_SECRET in .env (if using signature verification)
→ Check document_vault table: SELECT * FROM document_vault WHERE source='email' ORDER BY created_at DESC;
```

---

## 📋 Files That Need Updates

### `.env` (your backend environment file)
```bash
# Issue #1: Already configured (Supabase)
SUPABASE_URL=your_url
SUPABASE_SERVICE_ROLE_KEY=your_key

# Issue #2: Bland AI
BLAND_AI_API_KEY=bld_xxxxxxxxxxxx  # Get from Bland dashboard
BLAND_AI_ORG_ID=org_xxxxxxxxxxxx
BLAND_AI_WEBHOOK_SECRET=whsec_xxxxxxxxxxxx

# Issue #3: SendGrid
SENDGRID_API_KEY=SG.xxxxxxxxxxxx
SENDGRID_INBOUND_EMAIL=loads@3lakeslogistics.com
SENDGRID_INBOUND_SECRET=<optional>
```

### Database Schema
- Run: `sql/driver_schema_additions.sql` in Supabase SQL Editor

### Backend Routes (already implemented)
- ✅ `routes_prospecting.py` → `/api/prospecting/call` (Bland AI)
- ✅ `email_ingest.py` → `/api/webhooks/email/inbound` (SendGrid)

---

## 🚀 After All 3 Are Fixed

Your system will support:
✅ Driver mobile app (messages, sessions, payouts)
✅ Vance Dialer (call any prospect from EAGLE EYE)
✅ Document Vault (auto-sync invoices & contracts from email)

Next steps:
1. Build & sign mobile app for App Store/Play Store
2. Run E2E tests (login → load board → payout)
3. Load test with 100+ concurrent drivers
4. Deploy to production

---

**Last Updated**: 2026-05-15
**Status**: Ready for deployment

# Get Supabase Credentials in 2 Minutes

## Step 1: Go to Supabase Dashboard
1. Visit: https://app.supabase.com/
2. Sign in with your account
3. Select your 3 Lakes project

## Step 2: Copy the Project URL

**Location:** Settings → General → API

Look for **Project URL** - it looks like:
```
https://YOUR_PROJECT_ID.supabase.co
```

Copy this entire URL.

## Step 3: Copy the API Keys

In the same **Settings → General → API** section, you'll see:

### **SUPABASE_ANON_KEY**
- Label: "Anon (public)" or "Public key"
- Starts with: `eyJhbGc...`
- Copy this (it's safe to expose publicly)

### **SUPABASE_SERVICE_ROLE_KEY**
- Label: "Service Role (secret)" or "Secret key"
- Starts with: `eyJhbGc...` (longer than anon key)
- ⚠️ **KEEP THIS SECRET** - do NOT share or expose

## Step 4: Put Them in `.env`

Create or edit `/home/user/3-Lakes-Logistics/.env`:

```bash
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_ANON_KEY=eyJhbGc...your_anon_key...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...your_service_role_key...
```

## Step 5: Verify

```bash
grep SUPABASE /home/user/3-Lakes-Logistics/.env
```

Should show all 3 lines filled in.

---

## Where Exactly in Dashboard

1. **Left sidebar** → Click project name dropdown
2. **Select your project** (3 Lakes Logistics)
3. **Bottom left** → Settings (gear icon)
4. **Settings panel** → API
5. **You'll see:**
   - Project URL (at top)
   - Anon key (under "Anon (public)")
   - Service Role key (under "Service Role (secret)")

---

## Visual Indicator

Once you have all 3, your `.env` file should look like:

```
SUPABASE_URL=https://abc123xyz.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Once you have these 3, reply with "✅ DONE"** and I'll get the other credentials.

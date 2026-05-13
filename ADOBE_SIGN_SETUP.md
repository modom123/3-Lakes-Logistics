# Adobe Sign API Credential Retrieval Guide

## Step 1: Log Into Adobe Sign Admin Console

1. Go to https://secure.na1.adobesign.com/
2. Sign in with your Adobe account credentials
3. Click your **Profile icon** (top right) → **Account Settings**

## Step 2: Get Your Account ID

In Account Settings:
1. Look for **Account ID** (or **Company Account ID**)
2. It looks like: `CBJCHBCAABAAxxxxxxxxxxxxxxx` (long alphanumeric string)
3. **Copy and save this** — you'll need it

Alternatively, in the left sidebar:
- Click **Manage Account** → **Account Info**
- Account ID will be displayed prominently

## Step 3: Create API Key (OAuth 2.0 - Recommended)

In Account Settings, find **Integration** section:

1. Click **Manage APIs** or **Integration & APIs**
2. Click **Create New Application** or **Add Application**
3. Fill in:
   - **Application Name:** "3 Lakes Logistics Integration"
   - **Redirect URI:** `http://localhost:8080/api/adobe/callback` (for testing)
     - For production: `https://your-domain.com/api/adobe/callback`
   - **Scopes needed:** Select:
     - ✅ `agreement_read`
     - ✅ `agreement_write`
     - ✅ `agreement_send`
     - ✅ `user_read`

4. Click **Save**
5. You'll get:
   - **Client ID** (looks like: `CBJCHBCAABAAxxxxxxx`)
   - **Client Secret** (looks like: `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
   
   **⚠️ Copy these immediately — you won't see them again!**

## Step 4: Get API Endpoint

Your API endpoint is one of these (based on your region):
- **North America:** `https://api.na1.adobesign.com`
- **Europe:** `https://api.eu1.adobesign.com`
- **APAC:** `https://api.ap1.adobesign.com`

Most US accounts use `na1`.

---

## What You'll Get (Summary)

You'll need these 4 values:

```
ADOBE_ACCOUNT_ID=CBJCHBCAABAAxxxxxxx
ADOBE_CLIENT_ID=CBJCHBCAABAAxxxxxxx
ADOBE_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ADOBE_API_ENDPOINT=https://api.na1.adobesign.com
```

---

## Verification (Optional)

To test your credentials work:

```bash
curl -X GET "https://api.na1.adobesign.com/api/rest/v6/users/me" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Accept: application/json"
```

(We'll get access token in the backend setup)

---

## Next Steps Once You Have Credentials

1. Provide me with the 4 values above
2. I'll integrate Adobe Sign into the intake form
3. I'll create the webhook handler
4. Test e-signature flow end-to-end

---

## FAQ

**Q: Do I need a paid Adobe Sign plan?**
A: Yes, you need at least a basic plan with API access. Free trials work too.

**Q: Where's the "Integration" menu?**
A: It's in **Account Settings** → **Manage Account** → look for **Integration & APIs** or **Manage APIs**

**Q: Can I use Service Account instead of OAuth?**
A: Yes, but OAuth 2.0 is easier. Service Account requires JWT tokens.

**Q: What if I don't see the option to create applications?**
A: Contact Adobe Sign support — your account may need API access enabled first.

---

Go ahead and retrieve these values, then paste them here and I'll wire up the full integration! 🚀

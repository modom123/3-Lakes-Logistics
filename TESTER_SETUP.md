# Tester Setup Guide — 3 Lakes Driver App

---

## 1. TEST DRIVER ACCOUNTS (Database)

Run `sql/test_accounts.sql` in your **Supabase SQL Editor**:
1. Go to supabase.com → your project → **SQL Editor**
2. Paste contents of `sql/test_accounts.sql`
3. Click **Run**

### Test Login Credentials

| Name | Phone | PIN | Use For |
|------|-------|-----|---------|
| James Test Driver | 555-000-0001 | **1234** | Full feature testing |
| Maria Test Driver | 555-000-0002 | **5678** | Stripe onboarding flow |
| Bob Inactive | 555-000-0003 | **0000** | Test login block (inactive) |

### Pre-built Test Tokens (for API testing)
```
James: test_token_driver_001_james
Maria: test_token_driver_002_maria
```
Use in `Authorization: Bearer <token>` header.

---

## 2. BACKEND API TESTS

```bash
# Start backend
cd backend
uvicorn app.main:app --reload --port 8080

# In another terminal, run tests
python3 tests/test_driver_api.py
```

Tests cover: health, auth (valid/invalid PIN, inactive), GPS, payouts, notifications, security.

---

## 3. STRIPE TEST ACCOUNT

1. Go to **dashboard.stripe.com** → make sure toggle says **Test mode** (top right)
2. Use these test cards for payout testing:

| Card | Number | Use |
|------|--------|-----|
| Success | `4242 4242 4242 4242` | Successful payment |
| Declined | `4000 0000 0000 0002` | Card declined |
| Insufficient funds | `4000 0000 0000 9995` | Funds error |

3. For bank payouts use routing `110000000` + account `000123456789`
4. All Stripe test data is free — no real charges

**Test Stripe Connect payout:**
```bash
curl -X POST http://localhost:8080/api/payout/request \
  -H "Authorization: Bearer test_token_driver_001_james" \
  -H "Content-Type: application/json" \
  -d '{"load_id": "cccccccc-0001-4000-c000-000000000001", "gross_amount": 1850}'
```
Expected: net = $1850 - $148 dispatch - $45 insurance = **$1,657.00**

---

## 4. FIREBASE TEST (Push Notifications)

1. Go to **console.firebase.google.com** → your project
2. Click **Messaging** → **Send your first message**
3. Title: `Test Load Offer`
4. Body: `New load available: CHI → LAX $1,850`
5. Target: **FCM registration token** → paste `fcm_test_token_driver_001`
6. Click **Send test message**

Or test via API:
```bash
curl -X POST http://localhost:8080/api/notifications/send \
  -H "Authorization: Bearer test_token_driver_001_james" \
  -H "Content-Type: application/json" \
  -d '{"driver_id": "aaaaaaaa-0001-4000-a000-000000000001", "title": "New Load", "body": "CHI to LAX — $1,850"}'
```

---

## 5. GOOGLE PLAY INTERNAL TESTERS

1. Go to **Google Play Console** → your app
2. Left menu → **Testing** → **Internal testing**
3. Click **Create new release** → upload your signed APK
4. Click **Testers** tab → **Create email list**
5. Add tester email addresses (up to 100 for internal testing)
6. Testers get an email with a link to download the app from Play Store

**Before adding testers:**
- Build signed APK in Android Studio (Build → Generate Signed Bundle/APK)
- Upload APK to Internal testing track first
- Testers must accept the testing invitation link

---

## QUICK TEST CHECKLIST

- [ ] Run `sql/test_accounts.sql` in Supabase
- [ ] Start backend: `uvicorn app.main:app --reload --port 8080`
- [ ] Run: `python3 tests/test_driver_api.py` → all green
- [ ] Open driver app → login with phone `555-000-0001` PIN `1234`
- [ ] Accept a load from the load board
- [ ] Send a test message
- [ ] Upload a test document (any photo)
- [ ] Request payout → verify $1,657 net
- [ ] Check push notification arrives on device

# Google Play Store Submission Guide — 3 Lakes Driver

**App:** 3 Lakes Driver  
**App ID:** com.threelakes.driver  
**Version:** 1.0.0  

---

## STEP 1 — Generate your signing keystore (one-time, do this first)

Run on your local machine (requires Java JDK):

```bash
bash scripts/generate-keystore.sh
```

This creates `3lakes-release.keystore`. **Never commit this file.**  
Store the file + passwords in a password manager — you need them forever to publish updates.

---

## STEP 2 — Add GitHub Secrets

Go to: `github.com/modom123/3-lakes-logistics` → **Settings → Secrets and variables → Actions**

Add these 4 secrets:

| Secret name | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | Base64 output printed by the keytool script |
| `ANDROID_KEY_ALIAS` | `threelakes` |
| `ANDROID_STORE_PASSWORD` | Keystore password you chose |
| `ANDROID_KEY_PASSWORD` | Key password you chose |

---

## STEP 3 — Trigger the Android build

Push any change to `main`, or go to:  
**GitHub → Actions → "Build Android AAB (Google Play)" → Run workflow**

Set:
- `version_code`: `1`  (increment this integer every new release)
- `version_name`: `1.0.0`

The workflow builds a signed `.aab` file and uploads it as a GitHub Actions artifact.  
Download it from the workflow run's artifacts section.

---

## STEP 4 — Create Google Play Developer Account ($25 one-time)

1. Go to **play.google.com/console**
2. Sign in with a Google account
3. Pay the $25 registration fee
4. Accept the Developer Distribution Agreement

---

## STEP 5 — Create the app in Play Console

1. Click **"Create app"**
2. Fill in:
   - **App name:** `3 Lakes Driver`
   - **Default language:** `English (United States)`
   - **App or game:** `App`
   - **Free or paid:** `Free`
3. Accept declarations and click **Create app**

---

## STEP 6 — Fill in Store Listing

### Main store listing

**Short description** (80 chars max):
```
Driver app for 3 Lakes Logistics — loads, pay, docs, GPS tracking
```

**Full description** (4000 chars max):
```
3 Lakes Driver is the official driver app for 3 Lakes Logistics carriers.

FEATURES:
• Load Board — View and accept/decline load offers in real time
• Current Load — Full load details with one-tap Google Maps navigation
• Hours of Service (HOS) — Track your driving hours and status
• Document Upload — Submit BOL, POD, lumper receipts from your phone camera
• Pay & Settlements — View earnings, deductions, and settlement history
• Stripe Payouts — Direct deposit to your bank account
• Messaging — Real-time dispatch communication thread
• Profile — CDL info, carrier status, performance score
• Offline Support — Queue messages and actions when off-network

Built specifically for professional truck drivers. Requires an active driver account with 3 Lakes Logistics.
```

### Graphics (already prepared in play-store-graphics/)

| Asset | File | Size |
|---|---|---|
| App icon | `play-store-graphics/icon_512x512.png` | 512×512 px |
| Feature graphic | `play-store-graphics/feature_graphic_1024x500.png` | 1024×500 px |
| Phone screenshot 1 | `play-store-graphics/screenshot_1_home.png` | Upload as-is |
| Phone screenshot 2 | `play-store-graphics/screenshot_2_loads.png` | Upload as-is |
| Phone screenshot 3 | `play-store-graphics/screenshot_3_pay.png` | Upload as-is |
| Phone screenshot 4 | `play-store-graphics/screenshot_4_messages.png` | Upload as-is |
| Phone screenshot 5 | `play-store-graphics/screenshot_5_documents.png` | Upload as-is |

---

## STEP 7 — App Content Ratings

Go to **Policy → App content** in Play Console.

### Content rating questionnaire answers:
- **Category:** Business
- **Violence:** None
- **Sexual content:** None
- **Profanity:** None
- **Controlled substances:** None
- **User-generated content:** No (only driver-to-dispatch messaging)

Expected rating: **Everyone (E)**

---

## STEP 8 — Data Safety Form

Go to **Policy → Data safety**

| Data type | Collected | Shared | Required | Encrypted |
|---|---|---|---|---|
| Location (precise) | Yes | No | Yes | Yes |
| Phone number | Yes | No | Yes | Yes |
| Photos/documents | Yes | No | No | Yes |
| Financial info | No (Stripe handles) | No | — | — |
| App activity | Yes | No | No | Yes |

**Data use:** App functionality only. No selling data to third parties.

Privacy policy URL: `https://threelakeslogistics.com/privacy-policy` (or Firebase Hosting URL)

---

## STEP 9 — Upload the AAB

1. Go to **Release → Production** (or start with **Internal testing** first — recommended)
2. Click **Create new release**
3. Upload the `.aab` file you downloaded from GitHub Actions
4. Set Release name: `1.0.0`
5. Add release notes:
   ```
   Initial release — load board, HOS tracking, document upload, Stripe payouts, real-time dispatch messaging.
   ```
6. Click **Save** → **Review release** → **Start rollout**

---

## STEP 10 — Wait for Google Review

- **Internal testing:** Usually instant
- **Production:** 1–3 business days for first release

You'll get an email when approved.

---

## Updating the App (future releases)

1. Make your code changes
2. Increment `versionCode` by 1 (e.g., 1 → 2) in the workflow dispatch inputs
3. Update `versionName` (e.g., 1.0.0 → 1.1.0)
4. Push to main / run the workflow
5. Download new AAB from GitHub Actions artifacts
6. Upload to Play Console as a new release

---

## After Android — iOS App Store

See `APP_STORE_SUBMISSION.md` (to be created). Requirements:
- Mac with Xcode (or GitHub Actions macOS runner)
- Apple Developer Account ($99/year)
- Run: `npm run build:mobile && npx cap add ios && npx cap sync ios`
- Open in Xcode: `npx cap open ios`
- Archive & upload via Xcode Organizer or `fastlane`

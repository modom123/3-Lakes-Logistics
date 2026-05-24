# Google Play Store Submission Guide — 3 Lakes Driver

**App:** 3 Lakes Driver  
**App ID:** `com.threelakes.driver`  
**Organization:** 3 Lakes Logistics  
**DUNS Number:** 145025174  
**Developer Email:** nwtcinvestment@gmail.com  
**Version:** 1.0.0  

> **For James Bond (installer):** Follow each step in order. All values are pre-filled — just copy/paste.

---

## STEP 1 — Generate the signing keystore (one-time)

On any machine that has Java installed, run:

```bash
bash scripts/generate-keystore.sh
```

When prompted:
- **Keystore password:** choose a strong password and save it in the password manager
- **Key password:** use the same password (simpler to manage)
- **First and Last Name:** `3 Lakes Logistics`
- **Organizational Unit:** `Operations`
- **Organization:** `3 Lakes Logistics`
- **City:** your city
- **State:** your state (e.g. `MI`)
- **Country Code:** `US`

This creates `3lakes-release.keystore`. **Never commit this file to git.**  
Save the file and both passwords in the company password manager — they are needed for every future update.

---

## STEP 2 — Add GitHub Secrets

Go to:  
**github.com/modom123/3-lakes-logistics → Settings → Secrets and variables → Actions → New repository secret**

Add these 4 secrets (the keystore value is printed by the script above):

| Secret name | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | The long base64 string printed by the script |
| `ANDROID_KEY_ALIAS` | `threelakes` |
| `ANDROID_STORE_PASSWORD` | Keystore password chosen in Step 1 |
| `ANDROID_KEY_PASSWORD` | Key password chosen in Step 1 |

---

## STEP 3 — Trigger the Android build

Go to:  
**github.com/modom123/3-lakes-logistics → Actions → "Build Android AAB (Google Play)" → Run workflow**

Set:
- `version_code`: `1`
- `version_name`: `1.0.0`

Click **Run workflow**. Wait ~5 minutes for it to complete.  
Download the `3lakes-driver-release-*.aab` file from the workflow artifacts.

---

## STEP 4 — Create Google Play Developer Account

> One-time setup. Costs $25 USD (credit card required).

1. Open **play.google.com/console** in a browser
2. Sign in with Google account: **nwtcinvestment@gmail.com**
3. Click **"Get started"**
4. Choose **"Organization"** (not Individual)
5. Fill in:
   - **Organization name:** `3 Lakes Logistics`
   - **DUNS Number:** `145025174`
   - **Contact email:** `nwtcinvestment@gmail.com`
   - **Website:** `https://threelakeslogistics.com` (or your current site URL)
   - **Phone:** your business phone
6. Pay the **$25 one-time registration fee**
7. Accept the Developer Distribution Agreement
8. Wait for DUNS verification email from Google (usually 1–3 business days)

> **Note:** Google verifies DUNS numbers against Dun & Bradstreet. If 145025174 is not yet in D&B, you may need to register at dnb.com first (free, takes 1–5 business days).

---

## STEP 5 — Create the app listing

Once your account is approved:

1. In Play Console, click **"Create app"**
2. Fill in:

| Field | Value |
|---|---|
| App name | `3 Lakes Driver` |
| Default language | `English (United States)` |
| App or game | `App` |
| Free or paid | `Free` |

3. Check both declaration boxes → click **"Create app"**

---

## STEP 6 — Fill in Store Listing

Go to **Grow → Store presence → Main store listing**

### Short description (80 chars — copy exactly):
```
Driver app for 3 Lakes Logistics — loads, pay, docs, GPS tracking
```

### Full description (copy exactly):
```
3 Lakes Driver is the official driver app for 3 Lakes Logistics carriers.

FEATURES:
• Load Board — View and accept/decline load offers in real time
• Current Load — Full load details with one-tap Google Maps navigation
• Hours of Service (HOS) — Track your driving hours and status
• Document Upload — Submit BOL, POD, and lumper receipts from your phone
• Pay & Settlements — View earnings, deductions, and settlement history
• Stripe Payouts — Direct deposit to your bank account
• Messaging — Real-time communication with dispatch
• Driver Profile — CDL info, carrier status, performance score
• Offline Support — Queue messages and actions when off-network

Built specifically for professional truck drivers. Requires an active driver account with 3 Lakes Logistics.

Contact: nwtcinvestment@gmail.com
```

### Upload graphics (all files are in play-store-graphics/):

| Asset | File to upload |
|---|---|
| App icon (512×512) | `play-store-graphics/icon_512x512.png` |
| Feature graphic (1024×500) | `play-store-graphics/feature_graphic_1024x500.png` |
| Phone screenshot 1 | `play-store-graphics/screenshot_1_home.png` |
| Phone screenshot 2 | `play-store-graphics/screenshot_2_loads.png` |
| Phone screenshot 3 | `play-store-graphics/screenshot_3_pay.png` |
| Phone screenshot 4 | `play-store-graphics/screenshot_4_messages.png` |
| Phone screenshot 5 | `play-store-graphics/screenshot_5_documents.png` |

---

## STEP 7 — App Content Rating

Go to **Policy → App content → Rating**

Answer the IARC questionnaire:
- **Category:** Business
- **Violence:** None
- **Sexual content:** None
- **Profanity:** None
- **Controlled substances:** None
- **User-generated content:** No

Expected rating: **Everyone (E)**  
Click **Submit** to get the rating certificate.

---

## STEP 8 — Data Safety Form

Go to **Policy → App content → Data safety**

Select the following:

**Location → Precise location**
- Collected: Yes | Shared: No | Required: Yes | Encrypted: Yes
- Purpose: App functionality (GPS load tracking)

**Personal info → Phone number**
- Collected: Yes | Shared: No | Required: Yes | Encrypted: Yes
- Purpose: App functionality (driver login)

**Files and docs → Photos and videos**
- Collected: Yes | Shared: No | Required: No | Encrypted: Yes
- Purpose: App functionality (BOL/POD upload)

**App activity → App interactions**
- Collected: Yes | Shared: No | Required: No | Encrypted: Yes
- Purpose: Analytics

**Privacy policy URL:** `https://threelakeslogistics.com/privacy-policy`  
(Or use the Firebase-hosted URL from your deployment)

**Does your app share data with third parties?** No  
**Do you sell user data?** No

---

## STEP 9 — Target Audience & App Access

Go to **Policy → App content → Target audience**
- **Target age group:** 18 and over

Go to **Policy → App content → App access**
- Select **"All or some functionality is restricted"**
- Click **"Add instructions"**
- Enter:
  - **Username/Phone:** `+1 (555) 000-0001` *(use a real test driver phone)*
  - **PIN:** `1234` *(or your test PIN)*
  - **Notes:** `Driver login app — phone number + PIN authentication. Test account is a demo driver profile.`

---

## STEP 10 — Upload the AAB and Release

Go to **Release → Testing → Internal testing** (do this first):

1. Click **"Create new release"**
2. Upload the `.aab` file downloaded from GitHub Actions (Step 3)
3. **Release name:** `1.0.0`
4. **Release notes:**
   ```
   Initial release of 3 Lakes Driver.
   
   Features: load board, real-time dispatch messaging, HOS tracking,
   document upload (BOL/POD), Stripe payouts, GPS tracking.
   ```
5. Click **Save** → **Review release** → **Start rollout to Internal testing**

Test the app on real Android phones using Internal testing.  
When confirmed working → go to **Release → Production** and repeat to go live.

---

## STEP 11 — Wait for Review

| Track | Review time |
|---|---|
| Internal testing | Instant — available immediately to testers |
| Closed testing (Alpha/Beta) | A few hours |
| Production | 1–3 business days (first release) |

Google will email **nwtcinvestment@gmail.com** when approved.

---

## Updating the App (future releases)

1. Make code changes on the branch
2. Run the GitHub Actions workflow with:
   - `version_code`: increment by 1 (e.g., `1` → `2`)
   - `version_name`: update (e.g., `1.0.0` → `1.1.0`)
3. Download the new AAB artifact
4. In Play Console → Release → Production → Create new release → upload new AAB

---

## After Android — iPhone (iOS App Store)

Requirements:
- **Apple Developer Account:** $99/year at developer.apple.com
- **Mac with Xcode** (or GitHub Actions macOS runner — we can set this up)
- Sign in with: **nwtcinvestment@gmail.com** (create Apple ID if needed)
- App ID: `com.threelakes.driver`

Build command:
```bash
npm run build:mobile
npx cap add ios
npx cap sync ios
npx cap open ios   # opens Xcode
```

Then in Xcode: **Product → Archive → Distribute App → App Store Connect**

We can set up a GitHub Actions iOS workflow similar to the Android one when ready.

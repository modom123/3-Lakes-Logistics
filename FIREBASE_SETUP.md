# Firebase Setup for 3 Lakes Driver App

## Project Details
- **Project ID:** `lakes-logistics-ffe6f`
- **App Name:** 3 Lakes Driver
- **Platforms:** Web (PWA) + Android (Capacitor)

## Deployment Options

### 1. Web/PWA Deployment (Firebase Hosting)
```bash
firebase login
firebase deploy --only hosting:driver-app
```
This deploys the driver-pwa app to Firebase Hosting.
**URL:** `https://driver-app---lakes-logistics-ffe6f.web.app`

### 2. Android App Distribution (Testing)
```bash
# After building APK in Android Studio:
firebase appdistribution:distribute \
  android/app/build/outputs/apk/release/app-release.apk \
  --release-notes "Driver App v1.0" \
  --testers "your-testers@email.com"
```

### 3. Firebase Test Lab (Real Device Testing)
```bash
firebase testlab:android-run \
  android/app/build/outputs/apk/debug/app-debug.apk \
  --device-ids=walleye \
  --os-versions=10 \
  --locales=en_US
```

## Quick Start

### Step 1: Authenticate
```bash
firebase login
```
(Opens browser for Google sign-in)

### Step 2: Deploy Web App
```bash
firebase deploy --only hosting:driver-app
```

### Step 3: View Hosting Dashboard
```bash
firebase open hosting
```

## Build Android App

### Step 1: Install Dependencies
```bash
npm install
```

### Step 2: Add Android Platform
```bash
npm run cap:add:android
npm run cap:sync
```

### Step 3: Build in Android Studio
```bash
npm run cap:open:android
```
Then in Android Studio:
- Build → Build Bundle(s) / APK(s) → Build APK(s)

### Step 4: Distribute APK
```bash
firebase appdistribution:distribute android/app/build/outputs/apk/release/app-release.apk
```

## Files Created
- `.firebaserc` — Project configuration
- `firebase.json` — Hosting & deployment settings

## Environment Variables
Add to `.env` (Firebase SDK config):
```bash
FIREBASE_API_KEY=your_api_key
FIREBASE_APP_ID=your_app_id
FIREBASE_PROJECT_ID=lakes-logistics-ffe6f
```

## Troubleshooting
- `firebase login` not working? Use `firebase login --no-localhost`
- Need to switch projects? Run `firebase use <project-id>`
- Reset authentication? Run `firebase logout && firebase login`

## Next Steps
1. Run `firebase login`
2. Run `firebase deploy --only hosting:driver-app`
3. Check Firebase Console for deployed URL
4. Build Android app and distribute via App Distribution

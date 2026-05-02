# 3 Lakes Driver — Android App

React Native (Expo) driver app for 3 Lakes Logistics. Replaces the PWA with a native Android experience.

## Features

- **Home** — Current load card, HOS gauge (Drive / Shift / 70hr Cycle), Confirm Pickup/Delivery with GPS, Report Issue
- **Loads** — Available load board with Accept / Pass, real-time refresh
- **Messages** — SMS-style chat with dispatch, load offer cards, 12-second polling, unread badge
- **Docs** — BOL, POD, and Lumper Receipt upload via camera or file picker
- **Profile** — CDL status with expiry warnings, performance metrics, carrier info, phone number for SMS dispatch, logout

## Quick Start (Development)

```bash
cd mobile
npm install
npx expo start --android     # requires Android emulator or device with Expo Go
```

## Build APK (for driver download)

Install EAS CLI and log in:

```bash
npm install -g eas-cli
eas login
```

Build a distributable APK:

```bash
npm run build:android:apk
```

This produces an APK at the EAS Build URL. Share the download link with drivers — no Google Play required.

For a production AAB (Google Play Store):

```bash
npm run build:android:aab
```

## Configuration

On first launch, drivers enter:
- **Name** — their full name
- **Driver ID** — e.g. `DRV-001` (from dispatch)
- **API Token** — bearer token from dispatch
- **Server URL** — backend base URL, e.g. `https://api.3lakeslogistics.com`
- **Cell Phone** — for SMS dispatch routing (can also be set in Profile)

## Tech Stack

- Expo SDK 51 / React Native 0.74
- React Navigation 6 (bottom tabs + native stack)
- AsyncStorage for local persistence
- expo-location — GPS for pickup/delivery confirmation
- expo-image-picker — camera and photo library
- expo-document-picker — PDF uploads
- expo-notifications — push notification support

## Project Structure

```
mobile/
├── App.js                    Entry point, auth state, providers
├── app.json                  Expo / Android config
├── eas.json                  EAS Build profiles
├── src/
│   ├── api.js                API service layer
│   ├── storage.js            AsyncStorage wrapper
│   ├── theme.js              Light theme colors, typography, spacing
│   ├── context.js            Auth and badge React contexts
│   ├── navigation/
│   │   └── AppNavigator.js   Auth stack + bottom tabs
│   └── screens/
│       ├── LoginScreen.js
│       ├── HomeScreen.js
│       ├── LoadsScreen.js
│       ├── MessagesScreen.js
│       ├── DocumentsScreen.js
│       └── ProfileScreen.js
```

## API Endpoints Used

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/fleet?status=in_transit&limit=1` | GET | Current load |
| `/api/fleet?status=booked&limit=30` | GET | Available loads |
| `/api/fleet/{id}` | PATCH | Accept load |
| `/api/telemetry/ping` | POST | GPS pickup/delivery event |
| `/api/telemetry/hos` | GET | Hours of Service |
| `/api/comms/thread/{phone}` | GET | Message thread |
| `/api/comms/send` | POST | Send message |
| `/api/comms/read/{phone}` | PATCH | Mark messages read |
| `/api/webhooks/driver_issue` | POST | Report breakdown/issue |

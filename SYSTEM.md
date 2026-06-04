# 3 Lakes Logistics — System Architecture

## Overview

3 Lakes Logistics operates a unified platform across seven components:

---

## Components

### 1. 3LL Website
**URL:** `https://www.3lakeslogistics.com`
Public-facing marketing and carrier acquisition site. Entry point for new carriers and drivers discovering 3 Lakes Logistics.

---

### 2. Execution Engine
Backend AI automation layer powering the entire operation. Runs 30+ named agents on scheduled cron jobs and event-driven triggers. Handles compliance sweeps, lead outreach, revenue reporting, onboarding automation, settlement processing, and more. Lives in `backend/app/` and is hosted on Render.

---

### 3. Eagle Eye
**Audience:** Internal staff — Mark Odom, CC Gulley, dispatchers, operations team
Staff operations dashboard. Full visibility into all carriers, all drivers, all loads, revenue, compliance, AI agent activity, and fleet map. Dispatch creates drivers and manages the fleet from here.

---

### 4. Falcon — Carrier
**Audience:** CDL truck drivers
**Files:** `driver-pwa/login.html` → `driver-pwa/index.html`
The truck driver home office. Available 24/7 from any device. Live data scoped to each individual driver — current load, HOS, earnings, messages from dispatch, document uploads, and pay history. Drivers set their own PIN on first login via a welcome SMS sent at account creation.

---

### 5. Falcon — Light Fleet
**Audience:** Gig, NEMT, courier, and executive drivers
**Files:** `driver-pwa/login-lf.html` → `driver-pwa/lf.html`
The light fleet driver home office. Same 24/7 availability and live data model as Falcon Carrier, scoped to each individual light fleet driver. Supports multi-platform earnings (Curri, Roadie, Modivcare, Veho, AxleHire, Blacklane, Lugg).

---

### 6. Mobile App — Carrier
**Audience:** CDL truck drivers
Native Android/iOS application for truck drivers. Packaged version of the Falcon Carrier PWA, distributed through the Play Store and App Store.

---

### 7. Mobile App — Light Fleet
**Audience:** Gig, NEMT, courier, and executive drivers
Native Android/iOS application for light fleet drivers. Packaged version of the Falcon Light Fleet PWA, distributed through the Play Store and App Store.

---

## How the Components Connect

```
                    ┌─────────────────────┐
                    │    3LL Website       │  ← Carrier/driver acquisition
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  Execution Engine    │  ← All automation & AI agents
                    │  (FastAPI + Render)  │
                    └──┬──────┬──────┬────┘
                       │      │      │
          ┌────────────▼─┐  ┌─▼────────────┐  ┌──────────────┐
          │  Eagle Eye   │  │  Supabase DB  │  │   Twilio /   │
          │  (Staff ops) │  │  + Realtime   │  │   Stripe /   │
          └──────────────┘  └─┬──────────┬─┘  │   ELDs etc.  │
                              │          │     └──────────────┘
               ┌──────────────▼─┐    ┌───▼──────────────┐
               │ Falcon Carrier  │    │ Falcon LF        │
               │ + Mobile App    │    │ + Mobile App     │
               │ (Truck drivers) │    │ (LF drivers)     │
               └─────────────────┘    └──────────────────┘
```

## Auth Summary

| Component | Auth Method |
|---|---|
| Eagle Eye | Supabase email + password (staff only) |
| Falcon Carrier | Phone + 4-digit PIN (set by driver on first login) |
| Falcon Light Fleet | Phone + 4-digit PIN (set by driver on first login) |
| Mobile Apps | Same as their respective Falcon portals |

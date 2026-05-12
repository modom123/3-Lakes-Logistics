# 3 Lakes Driver PWA v2

Progressive Web App for drivers in the Founders program. Optimized for iOS and Android with offline-first architecture.

## ✅ Features Implemented

### Navigation (6 Tabs)
- **Home** - Current load status, HOS monitoring, daily earnings
- **Loads** - Available loads with quick-accept, completed load history
- **Messages** - Real-time dispatch communication with polling (12s intervals)
- **Earnings** - Weekly breakdown, take-home calculation (gross - $300 Founders fee - insurance), YTD tracking
- **Compliance** - CDL expiry alerts (color-coded: red/yellow/green), maintenance schedule, insurance status
- **Profile** - CDL info, equipment tracking, quick support buttons

### Load Management
- Display current active load with full details (rate, miles, RPM, commodity, weight)
- Confirm pickup/delivery with GPS location capture
- View available loads with accept/decline workflow
- Load history with completed deliveries
- Navigation links to pickup/delivery addresses via Google Maps

### Earnings & Pricing
- **Founders Program**: $300/month flat fee (1-time, not weekly)
- Gross earnings calculation
- Insurance deduction (~$45 per load)
- Fuel advance tracking
- Take-home net calculation
- Weekly and year-to-date summaries
- 100% of load earnings (no commission)

### Compliance & Safety
- CDL status monitoring with expiry date tracking
- Alerts: Expired (red), Expiring <30 days (yellow), Valid (green)
- Maintenance schedule (oil change, tire rotation, pre-trip inspection)
- Insurance and authority license verification
- 24/7 roadside assistance quick-call link

### Telemetry & Tracking
- GPS location capture every 30 seconds when in-transit
- Hours of Service (HOS) monitoring with visual progress bars:
  - Drive time (11-hour limit)
  - Shift time (14-hour limit)
  - 70-hour cycle (168-hour window)
- Pickup/delivery event logging with geotags

### Communication
- Real-time messaging with dispatch
- Message history polling (12-second intervals)
- Support quick-links:
  - Breakdown/roadside assistance (24/7)
  - Dispatch office (Mon-Fri 6am-8pm CT)

### Documents & Files
- BOL (Bill of Lading) upload
- POD (Proof of Delivery) upload with signature capture
- Photo and PDF support

### User Experience
- Dark theme professional interface
- Mobile-first responsive design
- Safe area insets (notches, home bars)
- Toast notifications for actions
- Service worker for offline capability
- API failover (primary/backup servers with automatic switching)
- 10-second request timeout with fallback

## 🏗️ Architecture

### Storage
- **LocalStorage**: Driver ID, token, name, phone, CDL info, equipment numbers
- **API**: Load data, earnings, messages, compliance, HOS status

### API Endpoints
```
GET  /api/fleet                      - Load listing (filters: status, driver_id, limit)
GET  /api/fleet?status=in_transit    - Current load
PATCH /api/fleet/{loadId}            - Update load status
POST /api/telemetry/location         - GPS tracking
POST /api/telemetry/ping             - Event logging (pickup, delivery)
GET  /api/telemetry/hos              - HOS status query
GET  /api/comms/thread/{phone}       - Message history
POST /api/comms/send                 - Send message
POST /api/webhooks/driver_issue      - Issue reporting
```

### Failover Strategy
- Primary API: https://3lakes-api-primary.fly.dev
- Backup API: https://3lakes-api-backup.fly.dev
- Automatic switch on first failure, health check every 60s

## 📱 Installation

### For Production
Replace `/driver-pwa/index.html` with `/driver-pwa/index-v2.html`:
```bash
cp driver-pwa/index-v2.html driver-pwa/index.html
```

### For Testing
Access via `http://localhost:8080/driver` (or your server URL)

### Mobile Installation
1. Open app in mobile browser
2. Share menu → Add to Home Screen
3. Appears as standalone app with dark theme and native feel

## 🔧 Configuration

Update these constants in the `<script>` section if needed:
- `API_PRIMARY` - Primary API endpoint
- `API_BACKUP` - Backup API endpoint
- HOS limits (11 drive, 14 shift, 70 cycle)
- Founders fee: $300/month
- Insurance: $45/load
- Message polling: 12 seconds
- GPS tracking: 30 seconds when in-transit

## 🎨 Theme Variables (CSS)
```css
--bg: #0a0f1e (dark background)
--surface: #111827 (cards, surfaces)
--card: #1a2235 (card backgrounds)
--border: #2a3550 (borders)
--accent: #3b82f6 (blue - interactive)
--green: #22c55e (success, CDL valid)
--yellow: #f59e0b (warning, CDL expiring)
--red: #ef4444 (error, CDL expired)
--text: #f1f5f9 (main text)
--muted: #64748b (secondary text)
```

## 📊 Data Flow

1. **Load Acceptance**: Driver accepts available load → API updates status to 'dispatched'
2. **GPS Tracking**: On pickup confirmation, app starts 30s location polling
3. **HOS Update**: Queried every 30s when tracking is active
4. **Earnings**: Calculated from delivered loads, deductions for $300 Founders fee + insurance
5. **Compliance**: CDL expiry pulled from localStorage, alerts triggered automatically
6. **Messages**: Polled every 12s, shows real-time dispatch communication

## 🛡️ Security

- Auth token in localStorage (cleared on logout)
- Bearer token in all API headers
- XSS protection via HTML escaping (esc() function)
- HTTPS required for production
- CORS handled by backend

## 🚀 Deployment Checklist

- [ ] Update `/driver-pwa/index.html` from index-v2.html
- [ ] Configure API endpoints in backend
- [ ] Set up database views for fleet API
- [ ] Configure Supabase realtime (messages)
- [ ] Test on iOS Safari and Android Chrome
- [ ] Verify GPS permissions dialog works
- [ ] Test offline message queuing
- [ ] Configure PWA manifest icons
- [ ] Set up SSL certificate
- [ ] Monitor API failover health checks

## 📝 Notes

- All times in user's local timezone
- Founders fee is monthly (not deducted per load)
- Insurance estimate is $45/load (adjust based on actual costs)
- HOS times come from /api/telemetry/hos endpoint
- Driver data persists in localStorage (survives app restart)
- Service worker caches app shell for offline access

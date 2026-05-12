# Driver App Deployment Guide

Step-by-step instructions to deploy the 3 Lakes Driver PWA v2 to production.

## 📋 Pre-Deployment Checklist

- [ ] Backend API servers running (primary + backup)
- [ ] Supabase database configured with fleet data
- [ ] Authentication tokens working
- [ ] SSL certificates installed
- [ ] DNS configured
- [ ] CDN configured (optional, for static assets)

---

## Step 1: Review Design Against Mockups

The driver app has been built with all required features. Review against your design mockups:

**File to review:** `/driver-pwa/index-v2.html`

**Feature checklist:** See `DRIVER_APP_FEATURE_CHECKLIST.md`

**Features included:**
- 6-tab navigation (Home, Loads, Messages, Earnings, Compliance, Profile)
- Real-time load management with quick-accept
- Earnings breakdown with $300 Founders fee calculation
- CDL expiry monitoring with color-coded alerts
- GPS tracking and HOS monitoring
- Message communication with dispatch
- Document uploads (BOL/POD)
- Quick support buttons (roadside, dispatch)
- Founders program integration ($300/mo, 100% earnings)
- Professional dark theme UI
- Mobile-first responsive design

---

## Step 2: Update HTML File

Once design is approved, replace the active index.html:

```bash
cd /home/user/3-Lakes-Logistics/driver-pwa/

# Backup original
cp index.html index-v1-backup.html

# Deploy v2
cp index-v2.html index.html

# Verify
ls -la index.html
```

---

## Step 3: Configure API Endpoints

Edit `/driver-pwa/index.html` lines 559-562:

**Current:**
```javascript
const API_PRIMARY = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
  ? 'http://localhost:8080'
  : 'https://3lakes-api-primary.fly.dev';
const API_BACKUP  = 'https://3lakes-api-backup.fly.dev';
```

**Update to your production URLs:**
```javascript
const API_PRIMARY = 'https://your-primary-api.com';
const API_BACKUP  = 'https://your-backup-api.com';
```

---

## Step 4: Update Phone Numbers (Optional)

Edit lines 461 and 509-510 to update support numbers:

**Roadside Assistance:**
```html
<a href="tel:+18005551234" ...>
```

**Dispatch Office:**
```html
<a href="tel:+18005550911" ...>
```

---

## Step 5: Configure Service Worker

The app includes `sw.js` for offline support. Verify it's deployed:

```bash
# Check file exists
ls -la driver-pwa/sw.js

# Update cache version if needed
# Edit sw.js line with: const CACHE_NAME = 'fleet-app-v2'
```

---

## Step 6: Set Up PWA Icons & Splash Screens

Update `/driver-pwa/manifest.json`:

```json
{
  "name": "3 Lakes Driver",
  "short_name": "3LD",
  "start_url": "/driver",
  "display": "standalone",
  "background_color": "#0a0f1e",
  "theme_color": "#3b82f6",
  "orientation": "portrait",
  "icons": [
    {
      "src": "/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any"
    }
  ]
}
```

**Create icon files:**
- `/icons/icon-192.png` (192×192 PNG)
- `/icons/icon-512.png` (512×512 PNG)

---

## Step 7: Backend API Requirements

Ensure these endpoints are available:

### Fleet Management
```
GET /api/fleet?status=in_transit&limit=1
  Response: [{ load_number, status, origin_city, origin_state, dest_city, dest_state, 
              rate_total, miles, commodity, weight, pickup_address, delivery_address }]

GET /api/fleet?status=booked&limit=30
  Response: [{ id, load_number, origin_city, origin_state, dest_city, dest_state, 
              rate_total, miles }]

GET /api/fleet?status=delivered&limit=10
  Response: [{ origin_city, origin_state, dest_city, dest_state, rate_total }]

PATCH /api/fleet/{loadId}
  Body: { status: "dispatched" }
  Response: { success: true }
```

### Telemetry
```
GET /api/telemetry/hos?driver_id=DRV-001
  Response: { drive_remaining: 11, shift_remaining: 14, cycle_remaining: 70 }

POST /api/telemetry/location
  Body: { driver_id, lat, lng, accuracy, speed_mph, heading, ts }
  Response: { success: true }

POST /api/telemetry/ping
  Body: { driver_id, lat, lng, event }
  Response: { success: true }
```

### Communications
```
GET /api/comms/thread/{phone}
  Response: { messages: [{ direction, body, created_at }] }

POST /api/comms/send
  Body: { to, body, driver_id }
  Response: { success: true }
```

### Webhooks
```
POST /api/webhooks/driver_issue
  Body: { driver_id, issue, ts }
  Response: { success: true }
```

---

## Step 8: Deploy to Web Server

**Option A: Static hosting (Apache, Nginx)**

```bash
# Copy files to web root
cp -r driver-pwa/* /var/www/3lakeslogistics.com/driver/

# Set permissions
chmod 644 /var/www/3lakeslogistics.com/driver/*.html
chmod 644 /var/www/3lakeslogistics.com/driver/*.js
chmod 755 /var/www/3lakeslogistics.com/driver/

# Verify
curl https://3lakeslogistics.com/driver/
```

**Option B: Docker**

```dockerfile
FROM nginx:latest
COPY driver-pwa/ /usr/share/nginx/html/driver/
EXPOSE 80
```

```bash
docker build -t 3lakes-driver .
docker run -p 80:80 3lakes-driver
```

**Option C: Vercel/Netlify**

```bash
# Vercel
vercel --prod

# Netlify
netlify deploy --prod --dir driver-pwa/
```

---

## Step 9: Test on Devices

### Desktop Testing
```bash
# Local development
python -m http.server 8000  # or: python3 -m http.server 8000

# Open browser
open http://localhost:8000/driver-pwa/
```

### iOS Testing
1. Open Safari on iPhone
2. Navigate to: `https://your-domain.com/driver/`
3. Share menu (bottom center)
4. "Add to Home Screen"
5. Verify standalone mode (no browser UI)

### Android Testing
1. Open Chrome on Android
2. Navigate to: `https://your-domain.com/driver/`
3. Menu (three dots) → "Install app" or "Add to Home screen"
4. Verify standalone mode

### Test Scenarios
- [ ] Login with valid token
- [ ] Accept available load
- [ ] Confirm pickup (verify GPS popup)
- [ ] View earnings breakdown
- [ ] Check CDL expiry alert
- [ ] Send message to dispatch
- [ ] Upload BOL/POD
- [ ] Verify offline functionality (disable network)
- [ ] Test API failover (disable primary endpoint)

---

## Step 10: Monitor Deployment

### Error Tracking
```javascript
// Monitor console for errors
// Check API response logs
// Monitor GPS tracking health
// Track message delivery
```

### User Metrics
- **Session duration**: How long drivers stay in app
- **Feature usage**: Which tabs are most used
- **Load acceptance rate**: % of offered loads accepted
- **Message response time**: Dispatch communication latency
- **Error rate**: API failures, GPS failures, timeouts

### Performance Metrics
- **Page load time**: < 2 seconds target
- **API response time**: < 1 second target
- **GPS accuracy**: Should be < 50 meters
- **Message latency**: < 5 seconds target

---

## Step 11: Post-Deployment Tasks

- [ ] Send app link to drivers via email
- [ ] Create user guide/tutorial
- [ ] Set up support email for driver issues
- [ ] Monitor server logs for errors
- [ ] Check API response times
- [ ] Verify message delivery
- [ ] Confirm GPS tracking is working
- [ ] Review user feedback weekly

---

## Rollback Procedure (If Needed)

If issues are found:

```bash
cd /driver-pwa/

# Restore v1
cp index-v1-backup.html index.html

# Verify
curl https://your-domain.com/driver/

# Investigate issue
# Fix in index-v2.html
# Re-deploy when ready

cp index-v2.html index.html
```

---

## Troubleshooting

### "API connection failed"
- Verify API endpoints are accessible
- Check CORS headers on backend
- Verify token is valid
- Check network connectivity

### "GPS not working"
- Verify HTTPS is enabled (required for geolocation)
- Ensure user has granted location permission
- Check browser supports geolocation API
- Test on real device (simulator sometimes fails)

### "Messages not loading"
- Verify /api/comms endpoint
- Check phone number is stored correctly
- Verify message polling interval (12 seconds)
- Check backend database has messages

### "HOS showing wrong times"
- Verify /api/telemetry/hos endpoint
- Check HOS calculation logic in backend
- Verify time zones match

### "Offline doesn't work"
- Verify service worker is registered
- Check browser supports Service Workers
- Verify sw.js is deployed correctly
- Check browser cache settings

---

## Questions?

See documentation:
- `driver-pwa/README.md` - Feature documentation
- `DRIVER_APP_FEATURE_CHECKLIST.md` - Complete feature list
- Code comments in `/driver-pwa/index-v2.html`

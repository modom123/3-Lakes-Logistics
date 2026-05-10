# 3 Lakes Logistics API — Complete Endpoint Reference

All endpoints require Bearer token authentication:
```
Authorization: Bearer YOUR_API_TOKEN
```

---

## 📊 Dashboard & Analytics

### GET `/api/dashboard/kpis`
Get key performance indicators (MTD loads, revenue, unpaid invoices, etc.)

**Response:**
```json
{
  "total_carriers": 42,
  "active_carriers": 38,
  "mtd_loads": 127,
  "mtd_gross": 48200.50,
  "avg_rpm": 2.28,
  "mtd_dispatch_fees": 4820.05,
  "unpaid_invoices": 3,
  "unpaid_total": 7500.00
}
```

### GET `/api/dashboard/recent-loads?limit=10`
Get recent loads (default 10, max 50)

---

## 👥 Carriers

### GET `/api/carriers/?status=active&plan=founders&limit=200`
List all carriers with optional filters

### GET `/api/carriers/{carrier_id}`
Get carrier details (company info, compliance status, fleet)

### PATCH `/api/carriers/{carrier_id}/status?new_status=suspended`
Update carrier status (onboarding | active | suspended | churned)

---

## 🚛 Fleet Assets

### GET `/api/fleet/?carrier_id=xxx&status=available`
List trucks with optional filters

**Query Params:**
- `carrier_id` - Filter by carrier
- `status` - available | on_load | out_of_service | maintenance
- `limit` - Max results (default 1000)

### GET `/api/fleet/{fleet_id}`
Get truck details (specs, location, status, load history)

### PATCH `/api/fleet/{fleet_id}/status?new_status=maintenance`
Update truck status

---

## 📋 Invoices (NEW)

### POST `/api/invoices/`
Create invoice for a carrier

**Body:**
```json
{
  "carrier_id": "uuid",
  "load_id": "uuid (optional)",
  "invoice_number": "INV-2026-001",
  "amount": 2500.00,
  "description": "Rate confirmation for Load #L-1001",
  "due_date": "2026-05-15",
  "payment_method": "stripe_transfer",
  "notes": "Paid upon delivery"
}
```

### GET `/api/invoices/?carrier_id=xxx&status=unpaid&limit=50&offset=0`
List invoices with filters

**Query Params:**
- `carrier_id` - Filter by carrier
- `status` - unpaid | paid | overdue | cancelled
- `limit` - Results per page (default 50)
- `offset` - Pagination offset

**Response includes:**
- `days_overdue` - Auto-calculated if unpaid
- `status` - Auto-updates to "overdue" if past due_date

### GET `/api/invoices/{invoice_id}`
Get invoice with linked carrier & load details

### PATCH `/api/invoices/{invoice_id}`
Update invoice (status, amount, due_date, payment info)

**Body:**
```json
{
  "status": "paid",
  "payment_method": "stripe_transfer",
  "notes": "Paid on 2026-05-10"
}
```

### GET `/api/invoices/stats/summary`
Get invoice summary (totals, aging, by status)

**Response:**
```json
{
  "total_invoices": 42,
  "total_amount": 98500.00,
  "paid_invoices": 39,
  "paid_amount": 92000.00,
  "unpaid_invoices": 3,
  "unpaid_amount": 6500.00,
  "aged_unpaid": {
    "0-7d": 500.00,
    "8-14d": 2000.00,
    "15-30d": 3500.00,
    "30+d": 500.00
  }
}
```

---

## ⚙️ Automations (NEW)

### GET `/api/automations/?status=failed`
List all automations and their health status

**Status values:** ok | warning | failed

**Response includes:**
- `name` - Display name
- `status` - Current health
- `last_run` - Human-readable (e.g., "2m ago")
- `error_count` - Cumulative errors
- `consecutive_failures` - Current streak
- `affected_carriers` - How many carriers depend on this

### GET `/api/automations/{service_name}`
Get automation detail with recent run history

**Example:** `/api/automations/eld_sync_motive`

**Response:**
```json
{
  "automation": {
    "service_name": "eld_sync_motive",
    "display_name": "ELD Sync — Motive",
    "status": "ok",
    "last_check_at": "2026-05-10T14:32:00Z",
    "last_success_at": "2026-05-10T14:32:00Z",
    "error_message": null,
    "consecutive_failures": 0,
    "affected_carriers": 18
  },
  "recent_runs": [
    {
      "status": "ok",
      "duration_ms": 2340,
      "items_processed": 18,
      "run_at": "2026-05-10T14:32:00Z"
    }
  ]
}
```

### POST `/api/automations/{service_name}/report`
Report automation run results (called by background jobs)

**Body:**
```json
{
  "status": "ok",
  "duration_ms": 2340,
  "items_processed": 18,
  "affected_carriers": 18,
  "error_message": null
}
```

### GET `/api/automations/stats/summary`
Get summary of all automation statuses

**Response:**
```json
{
  "total": 14,
  "ok": 12,
  "warning": 1,
  "failed": 1,
  "failures": [
    { "service": "payout_processing" }
  ]
}
```

---

## 📈 Analytics (NEW)

### GET `/api/analytics/fleet/utilization`
Get current fleet utilization rate

**Response:**
```json
{
  "total_trucks": 127,
  "trucks_on_load": 87,
  "utilization_percent": 68.5,
  "available_trucks": 40
}
```

### GET `/api/analytics/carriers/performance?limit=10`
Get top carriers by revenue & utilization

**Response:**
```json
{
  "count": 5,
  "data": [
    {
      "carrier_id": "uuid",
      "company_name": "Sunshine Freight",
      "loads_mtd": 24,
      "revenue_mtd": 58000.00,
      "avg_rpm": 2.42,
      "utilization_percent": 87.5,
      "trucks": 8,
      "status": "active"
    }
  ]
}
```

### GET `/api/analytics/loads/summary?days=30`
Get load statistics for the period

**Query Params:**
- `days` - Period (default 30, range 1-365)

**Response:**
```json
{
  "period_days": 30,
  "total_loads": 127,
  "total_revenue": 287500.00,
  "avg_per_load": 2263.78,
  "by_status": {
    "delivered": 95,
    "in_transit": 18,
    "available": 14
  }
}
```

### GET `/api/analytics/compliance/summary`
Get overall compliance status across all carriers

**Response:**
```json
{
  "total_carriers": 42,
  "compliant": 38,
  "warnings": 3,
  "critical": 1,
  "compliance_rate_percent": 90.5
}
```

### GET `/api/analytics/revenue/trend?months=12`
Get monthly revenue trend

**Query Params:**
- `months` - Period (default 12, range 1-24)

**Response:**
```json
{
  "count": 12,
  "data": [
    { "month": "2025-11", "loads": 28, "revenue": 64800.00 },
    { "month": "2025-12", "loads": 34, "revenue": 79200.00 },
    ...
  ]
}
```

### GET `/api/analytics/equipment/mix`
Get fleet composition by equipment type

**Response:**
```json
{
  "total_trucks": 127,
  "data": [
    { "type": "dry_van", "count": 53, "percentage": 41.7 },
    { "type": "reefer", "count": 23, "percentage": 18.1 },
    { "type": "flatbed", "count": 19, "percentage": 15.0 },
    ...
  ]
}
```

---

## 📧 Email Management

### POST `/api/webhooks/email/inbound`
Webhook endpoint for SendGrid Inbound Parse (auto-triggered)

### GET `/api/email-log?limit=50&status=load_created&offset=0`
Get email ingest log

**Query Params:**
- `status` - received | load_created | low_confidence | error | archived
- `limit` - Results (default 50, max 200)
- `offset` - Pagination

### GET `/api/email-log/{email_id}`
Get email detail with extracted data and linked load

### GET `/api/email/sources`
Get email source breakdown (SendGrid vs Hostinger IMAP)

### POST `/api/email/imap/poll`
Manually trigger IMAP polling for Hostinger emails

### GET `/api/email/templates`
List all email templates

### POST `/api/email/templates/{template_name}`
Update email template

### POST `/api/email/send-test`
Send test email using configured template

---

## 🎯 Loads & Dispatch

### GET `/api/dashboard/recent-loads?limit=10`
Get recent loads (same as dashboard KPIs endpoint)

---

## 💳 Payouts

### POST `/api/payout/setup`
Initiate Stripe Connect onboarding for driver

### POST `/api/payout/request`
Request payout for completed load

### GET `/api/payout/history`
Get payout history (last 30)

---

## 🔔 Notifications

### POST `/api/notifications/register-fcm`
Register Firebase Cloud Messaging token

### POST `/api/notifications/send`
Send push notification to single driver

### POST `/api/notifications/broadcast`
Send push notification to multiple drivers

---

## 📱 Driver Management

### POST `/api/auth/driver/login`
Driver login (phone + PIN)

### DELETE `/api/auth/driver/logout`
Driver logout

### GET `/api/driver/location`
Get driver's current location (GPS)

### POST `/api/driver/location`
Update driver location (called every 30s)

### POST `/api/driver/documents/upload`
Upload driver documents (BOL, POD, insurance, etc.)

---

## Health & Status

### GET `/health`
API health check

### GET `/docs`
Swagger API documentation

### GET `/redoc`
ReDoc API documentation

---

## Error Responses

All errors return JSON with status code:

```json
{
  "detail": "error message"
}
```

**Common status codes:**
- `200` OK
- `201` Created
- `400` Bad Request (invalid data)
- `401` Unauthorized (missing/invalid token)
- `403` Forbidden (insufficient permissions)
- `404` Not Found
- `500` Server Error

---

## Database Tables Created

**New tables:**
- `invoices` — Billing records for carriers
- `automation_health` — Automation service status
- `automation_run_log` — Historical run records

**Views:**
- `invoices_with_aging` — Invoices with calculated days_overdue

---

## Backend Running

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Set environment variables (.env file)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=xxx
API_BEARER_TOKEN=change-me-in-prod

# Run with auto-reload
uvicorn app.main:app --reload --port 8080

# Production (gunicorn)
gunicorn app.main:app -w 4 -b 0.0.0.0:8080
```

---

**Last Updated:** 2026-05-10

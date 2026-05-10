# 3 Lakes Logistics — Hybrid Email Integration Setup

## Overview

The operational suite supports **two parallel email ingestion channels**:

1. **SendGrid Inbound Parse** — Brokers send rate confirmations via email to `loads@3lakes.logistics`
2. **Hostinger IMAP Polling** — Internal team communications, carrier inquiries, and internal rate requests

Both channels feed into the same **CLM (Contract Logic Machine) scanner pipeline**, which extracts load details and auto-creates load records.

---

## Architecture

```
┌─────────────────────┐          ┌──────────────────────┐
│  Broker Email       │          │  Internal/Carrier    │
│  (Rate Confirm)     │          │  Email (Hostinger)   │
└──────────┬──────────┘          └──────────┬───────────┘
           │                                │
           ▼                                ▼
     ┌──────────────┐            ┌──────────────────┐
     │  SendGrid    │            │  IMAP Poller     │
     │  Inbound     │            │  (5 min poll)    │
     │  Webhook     │            │                  │
     └──────┬───────┘            └────────┬─────────┘
            │                             │
            └─────────────┬───────────────┘
                         ▼
            ┌─────────────────────────┐
            │   Email Ingest Handler   │
            │  (Unified Processing)    │
            └──────────┬───────────────┘
                       ▼
            ┌──────────────────────────┐
            │  CLM Contract Scanner     │
            │  (Extract load details)   │
            └──────────┬────────────────┘
                       ▼
            ┌──────────────────────────┐
            │  Load Record Creation     │
            │  (If confidence > 90%)    │
            └──────────────────────────┘
```

---

## Setup: SendGrid (Brokers)

### 1. SendGrid Configuration

```bash
# Get your SendGrid API key from:
# https://app.sendgrid.com/settings/api_keys

SENDGRID_API_KEY=SG.xxxxxxxxxxxxx
SENDGRID_INBOUND_EMAIL=loads@3lakes.logistics
SENDGRID_INBOUND_SECRET=xxxxxxxxxxxxx  # Optional webhook signature verification
```

### 2. Set Up Inbound Parse Webhook

In SendGrid dashboard:
1. Go to **Settings → Inbound Parse**
2. Add your domain
3. Set **Inbound Parse URL** to:
   ```
   https://your-api.com/api/webhooks/email/inbound
   ```
4. Copy the **Verification Key** → Set as `SENDGRID_INBOUND_SECRET` in .env

### 3. Test SendGrid Inbound

```bash
curl -X GET http://localhost:8080/api/email-log
# Returns recent emails processed via SendGrid
```

---

## Setup: Hostinger IMAP (Internal Team + Carriers)

### 1. Get Hostinger IMAP Credentials

From your Hostinger control panel:
1. Go to **Email → Email Accounts**
2. Select your email account (e.g., `orders@yourdomain.com`)
3. Click **More Options**
4. Note:
   - **IMAP Server:** `imap.hostinger.com`
   - **Port:** `993` (SSL/TLS)
   - **Username:** Your full email address
   - **Password:** Your email password

### 2. Configure .env

```bash
HOSTINGER_IMAP_ENABLED=true
HOSTINGER_IMAP_HOST=imap.hostinger.com
HOSTINGER_IMAP_PORT=993
HOSTINGER_IMAP_USERNAME=orders@yourdomain.com
HOSTINGER_IMAP_PASSWORD=your_email_password
HOSTINGER_IMAP_POLL_INTERVAL_SECONDS=300  # 5 minutes
```

### 3. Restart the API

The background scheduler will automatically start polling every 5 minutes.

### 4. Verify Polling

Check logs:
```bash
tail -f logs/3ll.imap_poller.log
# Should show: "IMAP poll: X emails processed"
```

Or manually trigger a poll:
```bash
curl -X POST http://localhost:8080/api/email/imap/poll \
  -H "Authorization: Bearer YOUR_API_TOKEN"

# Response:
# {
#   "ok": true,
#   "status": "ok",
#   "emails_processed": 3
# }
```

---

## Email Flow Explained

### Broker Email → Load Record (SendGrid)

1. Broker sends rate confirmation PDF to `loads@3lakes.logistics`
2. SendGrid webhook → `/api/webhooks/email/inbound`
3. System extracts PDF text
4. CLM scanner analyzes contract → extracts:
   - Broker name
   - Load number
   - Origin/destination
   - Pickup/delivery dates
   - Rate, weight, commodity
5. If confidence > 90% → **auto-create load record**
6. Load appears on load board for driver assignment

### Internal Email → Load Record (Hostinger IMAP)

1. Email arrives at `orders@yourdomain.com` or internal account
2. IMAP poller detects unseen email every 5 minutes
3. Same CLM pipeline processes attachment PDFs
4. Load record created if high confidence
5. Flagged for review if low confidence

---

## Email Log & Monitoring

### View All Emails

```bash
curl http://localhost:8080/api/email-log \
  -H "Authorization: Bearer YOUR_API_TOKEN"

# Response includes:
# - from_email, to_email, subject
# - status (received, load_created, low_confidence, error)
# - source (sendgrid or hostinger_imap)
# - attachment_count, extracted_data
```

### Filter by Source

```bash
# SendGrid only
curl http://localhost:8080/api/email-log/source/sendgrid \
  -H "Authorization: Bearer YOUR_API_TOKEN"

# Hostinger IMAP only
curl http://localhost:8080/api/email-log/source/hostinger_imap \
  -H "Authorization: Bearer YOUR_API_TOKEN"
```

### View Source Statistics

```bash
curl http://localhost:8080/api/email/sources \
  -H "Authorization: Bearer YOUR_API_TOKEN"

# Response:
# {
#   "ok": true,
#   "data": {
#     "sendgrid": 45,
#     "hostinger_imap": 12,
#     "unknown": 0
#   }
# }
```

### Get Email Detail

```bash
curl http://localhost:8080/api/email-log/{email_id} \
  -H "Authorization: Bearer YOUR_API_TOKEN"

# Returns full email record + linked load (if created)
```

---

## Email Status Codes

| Status | Meaning |
|--------|---------|
| `received` | Email received, processing started |
| `load_created` | Load record successfully created (confidence > 90%) |
| `low_confidence` | PDF text extracted, but CLM confidence < 90% — flagged for review |
| `invalid_data` | Missing required fields (broker_name, etc.) |
| `error` | PDF extraction or processing failed |
| `archived` | Email processed and archived |

---

## Email Sources

| Source | Path | Frequency |
|--------|------|-----------|
| `sendgrid` | `/api/webhooks/email/inbound` | Real-time (webhook) |
| `hostinger_imap` | IMAP poller (background job) | Every 5 min (configurable) |

---

## Troubleshooting

### IMAP Connection Failed

**Error:** `IMAP connection failed: AUTH failed`

**Solution:**
- Verify Hostinger email account is active
- Check username is full email: `orders@yourdomain.com` (not just `orders`)
- Reset password if auth fails repeatedly
- Ensure SSL/TLS is enabled (port 993)

### No Emails Processing

**Problem:** IMAP polling enabled but no emails appear

**Solution:**
1. Verify `HOSTINGER_IMAP_ENABLED=true` in .env
2. Check logs: `grep imap_poller logs/*.log`
3. Manually trigger: `curl -X POST /api/email/imap/poll`
4. Verify INBOX has unseen emails

### Low Confidence Emails

**Problem:** Email processed but load not created (confidence < 90%)

**Solution:**
1. Check email_log for low_confidence status
2. View extracted data: `GET /api/email-log/{email_id}`
3. Review CLM extraction accuracy
4. Manually create load if data looks good

### PDF Text Extraction Fails

**Error:** `Failed to extract text from filename.pdf`

**Solution:**
- Ensure PyPDF2 is installed: `pip install PyPDF2`
- PDF must contain extractable text (not scanned image)
- Try online PDF text extractor to verify PDF readability

---

## Advanced Configuration

### Change IMAP Poll Interval

```bash
# Poll every 1 minute (faster ingestion, higher CPU)
HOSTINGER_IMAP_POLL_INTERVAL_SECONDS=60

# Poll every 15 minutes (slower, lower CPU)
HOSTINGER_IMAP_POLL_INTERVAL_SECONDS=900
```

### Multiple IMAP Accounts

Currently supports one IMAP account. For multiple accounts:
1. Set up email forwarding from secondary accounts to primary
2. Or use Zapier/Make.com to forward to primary mailbox
3. Or modify `imap_poller.py` to support account array (future feature)

### Rate Limiting

SendGrid and Hostinger have rate limits:
- **SendGrid:** 100 emails/second
- **Hostinger:** Check with hosting provider

If hitting limits, increase `HOSTINGER_IMAP_POLL_INTERVAL_SECONDS`.

---

## Security Notes

⚠️ **Never commit `.env` to Git**

Sensitive credentials in `.env`:
- `SENDGRID_API_KEY`
- `HOSTINGER_IMAP_PASSWORD`
- `SENDGRID_INBOUND_SECRET`

Use:
- `.env.example` (template with dummy values)
- `.gitignore` entry: `.env`, `.env.local`, `.env.*.local`
- Secrets management (GitHub Secrets, Vercel Env, etc.)

---

## Email Database Schema

Required tables (auto-created by Supabase):

```sql
CREATE TABLE email_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_email TEXT NOT NULL,
  to_email TEXT,
  subject TEXT,
  body_text TEXT,
  body_html TEXT,
  attachment_count INT DEFAULT 0,
  status TEXT DEFAULT 'received',  -- received, load_created, low_confidence, error
  source TEXT DEFAULT 'sendgrid',  -- sendgrid, hostinger_imap
  confidence FLOAT,
  extracted_data JSONB,
  broker_name TEXT,
  load_id UUID REFERENCES loads(id),
  received_at TIMESTAMP,
  processed_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT now(),
  notes TEXT
);

CREATE INDEX idx_email_log_status ON email_log(status);
CREATE INDEX idx_email_log_source ON email_log(source);
CREATE INDEX idx_email_log_received_at ON email_log(received_at DESC);
```

---

## Next Steps

1. ✅ Configure SendGrid Inbound Parse webhook
2. ✅ Configure Hostinger IMAP credentials in .env
3. ✅ Restart API service
4. ✅ Test both channels with sample rate confirmations
5. ✅ Monitor email_log for successful load creation
6. Set up alerting for high error rates (optional)
7. Train CLM scanner with your broker PDFs (optional)

---

## API Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/webhooks/email/inbound` | POST | SendGrid webhook (auto) |
| `/api/email/imap/poll` | POST | Manually trigger IMAP poll |
| `/api/email-log` | GET | List recent emails |
| `/api/email-log/{id}` | GET | Get email detail + linked load |
| `/api/email/sources` | GET | Email source statistics |
| `/api/email-log/source/{type}` | GET | Filter by source (sendgrid\|hostinger_imap) |
| `/api/email/templates` | GET | List email templates |
| `/api/email/stats` | GET | Email processing stats |

---

**Last Updated:** 2026-05-10

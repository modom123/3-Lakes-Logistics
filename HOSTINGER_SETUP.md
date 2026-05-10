# 🚀 HOSTINGER EMAIL INTEGRATION — QUICK START

Your hybrid email integration is now **ready to use**. Here's the checklist:

## ✅ Completed Setup

- ✅ **Hostinger IMAP** configured: `info@3lakeslogistics.com`
- ✅ **SendGrid** channel still active for broker emails
- ✅ **Unified CLM pipeline** for both channels
- ✅ **Background scheduler** (polls every 5 minutes)
- ✅ **Email audit log** with source tracking
- ✅ **Admin API endpoints** for monitoring

## 📋 Next Steps

### 1. Verify IMAP Configuration (in your deployment environment)

```bash
cd backend
python3 verify_imap.py
```

**Expected output:**
```
✅ Connected to IMAP server
✅ Authentication successful
✅ Found X mailboxes
✅ ALL TESTS PASSED!
```

### 2. Start the API Server

```bash
cd backend
uvicorn app.main:app --reload --port 8080
```

**Watch for logs:**
```
INFO: APScheduler started — compliance@06:00 UTC, analytics@06:30 UTC
INFO: IMAP polling enabled — interval: 300s
```

### 3. Test IMAP Polling

**Manual trigger:**
```bash
curl -X POST http://localhost:8080/api/email/imap/poll \
  -H "Authorization: Bearer YOUR_API_TOKEN"
```

**Expected response:**
```json
{
  "ok": true,
  "status": "ok",
  "emails_processed": 0
}
```

### 4. Monitor Email Processing

```bash
# View all emails
curl http://localhost:8080/api/email-log \
  -H "Authorization: Bearer YOUR_API_TOKEN"

# View by source
curl http://localhost:8080/api/email/sources \
  -H "Authorization: Bearer YOUR_API_TOKEN"

# View only Hostinger emails
curl "http://localhost:8080/api/email-log/source/hostinger_imap" \
  -H "Authorization: Bearer YOUR_API_TOKEN"
```

## 📧 Email Accounts Configured

| Account | Purpose | Status |
|---------|---------|--------|
| `info@3lakeslogistics.com` | Primary IMAP polling | ✅ Active |
| `loads@3lakeslogistics.com` | SendGrid webhook | ✅ Active |

## 🔧 Configuration Details

```env
HOSTINGER_IMAP_ENABLED=true
HOSTINGER_IMAP_HOST=imap.hostinger.com
HOSTINGER_IMAP_PORT=993
HOSTINGER_IMAP_USERNAME=info@3lakeslogistics.com
HOSTINGER_IMAP_PASSWORD=***
HOSTINGER_IMAP_POLL_INTERVAL_SECONDS=300
```

## 🧪 Test Email Flow

1. **Send test email to** `info@3lakeslogistics.com`
2. **Attach PDF** with load details (rate confirmation)
3. **Wait 5 minutes** for IMAP polling to run
4. **Check email log:**
   ```bash
   curl http://localhost:8080/api/email-log \
     -H "Authorization: Bearer YOUR_API_TOKEN"
   ```
5. **Verify load created** if PDF confidence > 90%

## 📚 Documentation

- Complete setup guide: `backend/docs/EMAIL_INTEGRATION.md`
- Configuration template: `backend/.env.hostinger.example`
- Verification script: `backend/verify_imap.py`

## ⚠️ Security Notes

✅ `.env` is protected in `.gitignore`  
✅ Credentials NOT in version control  
✅ Use environment variables in production  
✅ Rotate passwords regularly  

## 🆘 Troubleshooting

### IMAP Connection Fails
```
❌ Address family not supported (network sandbox)
→ This is normal in test environments
→ Run verify_imap.py in your actual deployment
```

### No Emails Detected
1. Check INBOX has unseen emails
2. Verify `HOSTINGER_IMAP_ENABLED=true`
3. Check logs: `grep imap_poller logs/*.log`
4. Manually poll: `POST /api/email/imap/poll`

### Low Confidence Emails
- Check `email_log` for extracted data
- Review `GET /api/email-log/{email_id}`
- PDF may need better quality or formatting

## 📞 Support

- Email integration docs: `backend/docs/EMAIL_INTEGRATION.md`
- Test script: `python3 verify_imap.py`
- API endpoints: `GET /api/email-log`, `GET /api/email/sources`

---

**Ready to go!** 🎉

Start the API, send a test email, and watch the magic happen.

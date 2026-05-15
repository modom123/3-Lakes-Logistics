# Deployment Checklist — Vance Dialer + Document Vault

## Status Summary
- **Branch**: `claude/migrate-airtable-leads-eOcKI` (synced with main)
- **Feature**: Vance Dialer (self-service calling from EAGLE EYE) + Document Vault enhancements
- **Code Status**: ✅ Production-ready (all syntax valid, integrations in place)
- **Known Blockers**: IP allowlist on Bland AI account, SendGrid inbound parse not configured

---

## Pre-Deployment Verification

### Backend Code
- [x] `routes_prospecting.py`: `/api/prospecting/call` and `/api/prospecting/calls` endpoints implemented
- [x] `vance.py`: Agent wrapper properly calls bland_client
- [x] `bland_client.py`: Bland AI API integration with proper authentication and error handling
- [x] `routes_bland_webhooks.py`: Webhook endpoint at `/api/webhooks/bland` with signature verification
- [x] `email_ingest.py`: Document vault logging for inbound email attachments
- [x] `engine.py`: Document vault logging for generated invoices
- [x] `settings.py`: Environment variables defined (bland_ai_api_key, bland_ai_org_id)
- [x] Python syntax: All files compile without errors

### Frontend Code
- [x] `index.html`: Vance Dialer UI panel added to Agents page
- [x] `vanceCall()`: Phone validation, E.164 normalization, API call handling
- [x] `loadVanceCalls()`: Fetches recent calls from `/api/prospecting/calls`
- [x] Document Vault: Metrics, filtering, search functionality
- [x] UI/UX: Result display (success/error), recent calls table, proper styling

### Configuration
- [x] `.env.example`: Updated with Bland AI config
- [x] `settings.py`: bland_ai_api_key and bland_ai_org_id fields defined
- [x] Route registration: prospecting_router and bland_webhooks_router registered in main.py
- [x] Webhook registration: Email ingest and Bland webhooks registered

---

## Critical Path Testing

### Local Testing (Blocked by IP Allowlist)
- [ ] Call fires from EAGLE EYE manually (blocked — requires IP allowlist removal)
- [ ] Call appears in agent_log table (blocked — blocked by above)
- [ ] Webhook received from Bland AI (blocked — blocked by above)

### Production Testing (Once Deployed)
- [ ] Call fires from production EAGLE EYE instance
- [ ] Call appears in agent_log on production database
- [ ] Vance call completion triggers follow-up sequence (email + SMS)
- [ ] Manual call lead_id uniquely identifies each caller

---

## Production Deployment Steps

### 1. Bland AI Account Configuration
**ACTION REQUIRED**: User must perform in Bland AI dashboard at https://app.bland.ai

- [ ] Go to Account Settings → IP Allowlist
- [ ] **Option A**: Disable IP allowlist entirely (permissive)
- [ ] **Option B**: Add production server IP to allowlist (more secure)
- [ ] **Verify**: Test API key format — ensure BLAND_AI_API_KEY is not equal to BLAND_AI_ORG_ID
  - API key should be a different value than org ID
  - If values are identical, regenerate API key in Bland dashboard

### 2. SendGrid Configuration
**ACTION REQUIRED**: DNS + SendGrid dashboard setup

#### DNS Changes
- [ ] Add MX record for `loads.3lakeslogistics.com`: `mx.sendgrid.net` (priority 10)
- [ ] Verify DNS propagation (may take 24-48 hours)

#### SendGrid Dashboard
- [ ] Log in to app.sendgrid.com
- [ ] Go to Settings → Inbound Parse
- [ ] Create Inbound Parse webhook:
  - **Hostname**: `loads.3lakeslogistics.com`
  - **URL**: `https://your-api-domain.com/api/webhooks/email/inbound`
  - **POST the raw, full MIME message**: Yes (checked)
  - Test webhook to verify connectivity

### 3. Backend Deployment
**ACTION REQUIRED**: Set environment variables in production

In your production environment (Heroku, Cloud Run, Docker, etc.):

```bash
# Bland AI (from https://app.bland.ai dashboard)
BLAND_AI_API_KEY=your_actual_api_key_here
BLAND_AI_ORG_ID=org_...
BLAND_AI_WEBHOOK_SECRET=whsec_...

# SendGrid (if using signature verification)
SENDGRID_INBOUND_SECRET=your_sendgrid_verification_key

# Also verify existing vars are set:
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

Deploy backend with the above environment variables.

### 4. Frontend Deployment
Deploy the updated `index.html` with:
- Vance Dialer UI in Agents page
- Document Vault enhancements (filtering, search, metrics)

---

## Post-Deployment Verification

### Smoke Tests
1. **Vance Dialer UI**
   - [ ] Open EAGLE EYE → Agents page
   - [ ] Verify Vance Dialer panel is visible
   - [ ] Enter test name + phone + notes
   - [ ] Click "Call Now" button
   - [ ] Verify success message appears with call ID

2. **Recent Calls Table**
   - [ ] Verify recent calls appear in table below dialer
   - [ ] Check that call status is "started" (green badge)
   - [ ] Timestamp should show local time

3. **Document Vault**
   - [ ] Send test email with PDF to loads@3lakeslogistics.com
   - [ ] Verify PDF appears in Document Vault (pending status)
   - [ ] Once processed, verify status updates to "complete"

4. **Agent Log Audit Trail**
   - [ ] Check agent_log table for "manual_call" entries
   - [ ] Verify payload includes name, phone, lead_id
   - [ ] Verify result field shows "started" or error details

### Monitoring
- [ ] Set up error alerting for `/api/prospecting/call` failures
- [ ] Monitor Bland AI webhook delivery via Bland dashboard
- [ ] Track call completion rates in agent_log
- [ ] Monitor email ingest webhook in SendGrid dashboard

---

## Troubleshooting Guide

### Issue: "Host not in allowlist" from Bland AI
**Cause**: IP allowlist is enabled on Bland AI account
**Solution**: Disable in Bland dashboard or whitelist production server IP

### Issue: Calls don't appear in Recent Calls table
**Cause**: /api/prospecting/calls endpoint not returning data
**Solution**: 
1. Verify agent_log table has "vance" agent entries
2. Check backend logs for errors in routes_prospecting.py
3. Verify require_bearer auth token is being passed

### Issue: Email attachments not appearing in Document Vault
**Cause**: SendGrid webhook not configured or not reaching backend
**Solution**:
1. Verify DNS MX record is set and propagated
2. Verify SendGrid Inbound Parse webhook URL is correct
3. Check SendGrid dashboard for webhook delivery status
4. Check backend logs for email_ingest errors

### Issue: Bot doesn't complete call
**Cause**: Bland AI org_id or webhook_url not set correctly
**Solution**:
1. Verify BLAND_AI_ORG_ID is set in production .env
2. Test Bland webhook URL is accessible from internet
3. Check Bland dashboard call logs for call status
4. Review vance_follow_up.py for follow-up sequence errors

---

## Files Modified in This Session

- `backend/app/api/routes_prospecting.py`: Added `/call` and `/calls` endpoints
- `backend/app/agents/vance.py`: Added vance agent wrapper
- `backend/app/agents/bland_client.py`: Bland AI client integration
- `backend/app/clm/engine.py`: Added invoice to document_vault
- `backend/app/email_ingest.py`: Added email attachment to document_vault
- `backend/app/settings.py`: Added bland_ai_api_key, bland_ai_org_id
- `backend/.env.example`: Updated with Bland AI config
- `index.html`: Added Vance Dialer UI + document vault enhancements
- `vercel.json`: Fixed deprecated builds, added routes

---

## Notes

- **API Key Verification**: Both BLAND_AI_API_KEY and BLAND_AI_ORG_ID currently have the same value in `.env`. This may be incorrect. The user should verify in the Bland AI dashboard that the API key is different from the org ID.

- **Webhook Signature Secret**: BLAND_AI_WEBHOOK_SECRET is in .env.example but should be set to actual value from Bland dashboard for production.

- **Follow-up Automation**: Once calls complete, `vance_follow_up.py` will automatically email and SMS interested prospects. Ensure Twilio and email credentials are configured.

- **Load Board Integration**: The prospecting pipeline can auto-call high-scoring leads if `auto_call=true` is passed to `/api/prospecting/run`. Manual calls via EAGLE EYE use the new `/api/prospecting/call` endpoint.

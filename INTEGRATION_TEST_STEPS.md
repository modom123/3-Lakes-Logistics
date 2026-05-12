# Integration Testing & Configuration — Next 4 Steps

## Overview
All backend infrastructure is built and ready. These 4 steps verify the integration is working end-to-end.

---

## Step 1: Deploy Demo Video ($300 Pricing Update)

**Status:** ✅ Script ready, needs local execution

**File:** `/backend/update_demo_pricing.py`  
**Input:** `/backend/demo-video-original.mp4` (23 MB, already in repo)  
**Output:** `/backend/demo.mp4` (ready for production)

### How to Run Locally

```bash
# 1. Install requirements (one-time)
brew install ffmpeg          # macOS
# or: sudo apt-get install ffmpeg  # Linux
# or: Download from https://ffmpeg.org/  # Windows

pip install pydub gtts       # Python packages

# 2. Navigate to backend
cd /path/to/3-Lakes-Logistics/backend

# 3. Run the script
python3 update_demo_pricing.py

# Expected output:
# ==================================================
# 3 Lakes Logistics Demo Video — Pricing Update
# ==================================================
# 🎙️  Generating new pricing voiceover ($300/month)...
# ✓ Pricing voiceover generated: pricing_segment_300.mp3
# 🔊 Extracting audio from video...
# 🔄 Replacing pricing audio segment...
# 🎬 Rebuilding video with updated audio...
# ✓ Video complete: demo.mp4
# ==================================================
# ✅ SUCCESS! Updated demo video ready
# ==================================================

# 4. Deploy the updated video
# Upload demo.mp4 to your web server:
# scp demo.mp4 your_server:/var/www/3lakeslogistics.com/
```

**Verification:**
- [ ] File `demo.mp4` created in `/backend/`
- [ ] File size ~22-24 MB
- [ ] Video plays and mentions "$300/month" (not $200)
- [ ] Upload to https://3lakeslogistics.com/demo.mp4

**Used in:** Follow-up email (auto-included after Vance call)

---

## Step 2: Test Bland AI Integration

**Status:** ✅ Code complete, needs API key + configuration

**Configuration Required:**
1. Get API key from Bland AI dashboard
2. Register webhook URL
3. Set environment variables
4. Make test call

### Setup Instructions

**Step 2a: Get Bland AI API Key**

1. Visit: https://bland.ai/
2. Sign up or log in
3. Go to Dashboard → Settings → API Keys
4. Copy your API key

**Step 2b: Configure Environment**

Edit `.env` in project root:
```bash
# Bland AI Configuration
BLAND_AI_API_KEY=your_api_key_here
BLAND_AI_WEBHOOK_SECRET=your_webhook_secret_here
```

**Step 2c: Register Webhook URL**

In Bland AI dashboard:
1. Settings → Webhooks
2. Add webhook URL: `https://your-api.com/api/webhooks/bland`
3. Copy the webhook secret into `.env` above

**Step 2d: Test with a Call**

```bash
# From within backend directory
python3 -c "
from app.agents.bland_client import start_outbound_call

result = start_outbound_call(
    lead_id='test_001',
    phone='+15551234567',  # Replace with test number
    prospect_name='John Doe',
    prospect_email='john@example.com',
    company_name='Doe Trucking',
    dot_number='1234567',
    webhook_url='https://your-api.com/api/webhooks/bland'
)
print(result)
"
```

### What Happens in a Vance Call

1. **Outbound Call**: Vance calls prospect via Bland AI ($0.06/min base rate)
2. **Conversation**: Claude Opus powers voice AI, asks about:
   - How long running own authority?
   - Fleet size
   - Current dispatch situation
   - Pain points
3. **Qualification**: Vance listens for interest signals
4. **Offer**: If interested, offers 15-min call with Commander
5. **Webhook**: Bland AI sends `call.completed` event with:
   - Transcript
   - Duration (for cost calculation)
   - Analysis (success=true/false)
   - Metadata (lead_id, prospect_name, etc)
6. **Auto Follow-up**: If qualified as interested:
   - Email with demo video + booking link (immediate)
   - SMS reminder in 24 hours (if no booking)

### Webhook Event Example

```json
POST /api/webhooks/bland
{
  "event": "call.completed",
  "call_id": "call_abc123xyz",
  "phone_number": "+15551234567",
  "duration": 147,
  "transcript": "Vance: Hi John, how long you been... John: Yeah, about 5 years...",
  "analysis": {
    "success": true,
    "reason": "Prospect expressed interest in demo call"
  },
  "metadata": {
    "lead_id": "lead_123",
    "prospect_name": "John Doe",
    "prospect_email": "john@example.com",
    "company_name": "Doe Trucking",
    "dot_number": "1234567"
  }
}
```

**Verification:**
- [ ] API key added to .env
- [ ] Webhook secret added to .env
- [ ] Webhook URL registered in Bland AI
- [ ] Test call completes successfully
- [ ] Webhook event received by backend
- [ ] Call transcribed in logs
- [ ] Analysis saved to database

**Cost:** $0.06/minute base + Claude LLM tokens (~$0.10 per call average)

**Files:**
- `backend/app/agents/bland_client.py` - Call initiation
- `backend/app/api/routes_bland_webhooks.py` - Webhook receiver
- `backend/app/agents/vance.py` - Call orchestration
- `backend/app/agents/vance_follow_up.py` - Auto-triggered follow-up

---

## Step 3: Configure Calendly

**Status:** ✅ Already configured, just verify

**Current Setup:**
```
Calendly URL: https://calendly.com/3lakes/commander-call
Duration: 15 minutes (recommended)
Used in: Follow-up email and SMS
```

### Verification Steps

1. **Test Link**
   - Visit: https://calendly.com/3lakes/commander-call
   - Verify page loads
   - Check 15-minute duration
   - Test booking (should receive confirmation)

2. **Email Integration**
   - In follow-up email: "📅 Book Your Demo Call" button links to Calendly
   - See: `backend/app/prospecting/follow_up.py` line 97

3. **SMS Integration**
   - In SMS reminder: Calendly link included
   - See: `backend/app/prospecting/follow_up.py` line 193

### Update if Needed

If you need to use a different Calendly link:

**File:** `backend/app/prospecting/follow_up.py` (line 20)
```python
CALENDLY_BOOKING_URL = "https://calendly.com/your-name/your-event"
```

### Calendly Configuration Recommended

In Calendly settings:
- [ ] Event type: "Commander Demo Call"
- [ ] Duration: 15 minutes
- [ ] Calendar: Synced to your team's Google/Outlook
- [ ] Confirmation: Auto-email to prospect
- [ ] Reminder: SMS + email 1 hour before
- [ ] Questions: Ask about their truck/authority status
- [ ] Connected email: `commander@3lakeslogistics.com` (or similar)

**Verification:**
- [ ] Link works from browser
- [ ] Booking creates calendar event
- [ ] Prospect receives confirmation email
- [ ] Commander/team gets notification

---

## Step 4: Test SMS & Email Delivery

**Status:** ✅ Code complete, needs API credentials

**Services Used:**
- **Email**: Postmark (industry standard for transactional)
- **SMS**: Twilio (carrier relationships for delivery)

### Step 4a: Setup Postmark (Email)

1. Visit: https://postmarkapp.com/
2. Sign up or log in
3. Create new server: "3 Lakes Logistics"
4. Copy **Server Token** (looks like: `xxxxxxxxxxxxxxxxxxxxxxxx`)
5. Verify sender email: `ops@3lakeslogistics.com` (or your domain)

Add to `.env`:
```bash
POSTMARK_SERVER_TOKEN=your_server_token_here
POSTMARK_FROM_EMAIL=ops@3lakeslogistics.com
```

### Step 4b: Setup Twilio (SMS)

1. Visit: https://www.twilio.com/
2. Sign up or log in
3. Buy a phone number (e.g., +1-800-TRUCKS-1)
4. Copy **Account SID** and **Auth Token** from dashboard
5. Get your **phone number** (the "From" number)

Add to `.env`:
```bash
TWILIO_ACCOUNT_SID=your_account_sid_here
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_FROM_NUMBER=+18005551234
```

### Step 4c: Test Email Delivery

```bash
python3 << 'EOF'
from app.prospecting.follow_up import send_follow_up_email

result = send_follow_up_email(
    lead_id="test_001",
    prospect_name="John Doe",
    prospect_email="john@example.com",  # Use test email
    company_name="Doe Trucking",
    phone_number="+15551234567"
)

print("Email Result:", result)
# Expected: {"status": "sent", "message_id": "..."}
EOF
```

**Check:**
- [ ] Email arrives in inbox
- [ ] From: ops@3lakeslogistics.com
- [ ] Subject: "Your 3 Lakes Founders Program Demo — John Doe"
- [ ] Contains demo video link
- [ ] Contains Calendly booking link
- [ ] Shows Founders benefits ($300/mo, 100% earnings, etc)

### Step 4d: Test SMS Delivery

```bash
python3 << 'EOF'
from app.prospecting.follow_up import send_sms_reminder

result = send_sms_reminder(
    lead_id="test_001",
    prospect_name="John Doe",
    phone_number="+15551234567"  # Use test number
)

print("SMS Result:", result)
# Expected: {"status": "sent", "message_sid": "..."}
EOF
```

**Check:**
- [ ] SMS arrives on phone
- [ ] From: Your Twilio number
- [ ] Message: Includes prospect name, $300/mo, Calendly link
- [ ] Delivery within 5 seconds

### Integration Flow

```
Vance calls prospect
  ↓
Call completes, webhook arrives
  ↓
Webhook handler checks: success=true?
  ↓
YES → Trigger vance_follow_up.py
  ↓
  ├─ send_follow_up_email() [immediate]
  │  └─ Prospect receives email with video + Calendly
  │
  └─ schedule_follow_up_reminder() [24h later]
     └─ Check if booking made yet
        └─ If NO booking → send_sms_reminder()
           └─ Prospect receives SMS with Calendly link
```

### Costs

**Email (Postmark):**
- $10/month for 25,000 emails
- $20/month for 100,000 emails
- ~$0.0004 per email

**SMS (Twilio):**
- ~$0.0075 per SMS sent (US)
- ~$0.0075 per SMS received
- Phone number: ~$1/month

**Total for 1000 prospects:**
- Email: ~$0.40
- SMS: ~$15 (if all book and receive reminder)
- **Cost per conversion: ~$0.015 - $0.02**

### Verification Checklist

**Email:**
- [ ] Postmark server token in .env
- [ ] Sender email verified
- [ ] Test email arrives in inbox
- [ ] Links clickable
- [ ] Template renders correctly
- [ ] Metadata logged (lead_id)

**SMS:**
- [ ] Twilio account SID in .env
- [ ] Auth token in .env
- [ ] Phone number in .env
- [ ] Test SMS arrives on phone
- [ ] Message within character limit
- [ ] Calendly link clickable from SMS

**Integration:**
- [ ] Webhook triggers follow-up
- [ ] Email sent immediately (< 5s)
- [ ] SMS scheduled for 24h
- [ ] Both logged to database

---

## Testing Timeline

**Day 1:**
- [ ] Bland AI API key acquired + configured
- [ ] Demo video script runs locally
- [ ] Postmark + Twilio accounts created

**Day 2:**
- [ ] Test email delivery
- [ ] Test SMS delivery
- [ ] Make 3-5 test Bland AI calls

**Day 3:**
- [ ] Verify webhook processing
- [ ] Check auto follow-up trigger
- [ ] Verify Calendly integration

**Day 4+:**
- [ ] Monitor first 10-20 real calls
- [ ] Check conversion rate (booking %)
- [ ] Adjust messaging if needed

---

## Troubleshooting

**Bland AI call fails:**
- Check API key is valid
- Verify phone number format (+1...)
- Check account has credits
- Review call logs in Bland dashboard

**Email not arriving:**
- Verify sender email is verified in Postmark
- Check spam folder
- Review Postmark bounce logs
- Verify POSTMARK_SERVER_TOKEN in .env

**SMS not arriving:**
- Verify phone number is correct
- Check Twilio account has credits
- Review Twilio message logs
- Verify TWILIO_FROM_NUMBER is valid

**Webhook not triggering:**
- Check webhook URL is publicly accessible
- Verify signature verification passes
- Check backend logs for errors
- Test webhook directly: `POST /api/webhooks/bland/health`

---

## Next Steps After Testing

1. **Launch Tier 3** - Start making 10-20 prospecting calls per day
2. **Monitor funnel** - Track: calls → interested → emails → bookings → sales
3. **Optimize messaging** - Adjust Vance prompt based on conversation patterns
4. **Scale gradually** - Increase from 20 → 100 → 1000 calls/month as confidence grows
5. **Track metrics** - Cost per lead, conversion rate, time to booking

---

## Files Reference

**Demo Video:**
- `backend/update_demo_pricing.py` - Update script
- `backend/DEMO_VIDEO_UPDATE.md` - Setup guide

**Bland AI:**
- `backend/app/agents/bland_client.py` - Call client
- `backend/app/api/routes_bland_webhooks.py` - Webhook handler
- `backend/app/agents/vance.py` - Agent orchestration

**Follow-up:**
- `backend/app/prospecting/follow_up.py` - Email + SMS
- `backend/app/agents/vance_follow_up.py` - Auto-trigger (Step 36)

**Settings:**
- `backend/app/settings.py` - All API key definitions
- `.env` - Where to put actual credentials

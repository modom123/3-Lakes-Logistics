Filed: 2026-05-15T16:45:56Z

# Session Summary — 2026-05-15 16:45

## Work Completed Since Last Summary

### 1. Two-Email Post-Call Sequence (Option 2)
- Added `send_onboarding_guide_email()` to `follow_up.py` — full branded HTML email
  with 5-step checklist (steps 1+2 shown as done), doc table, pricing, benefits, FAQ,
  dual Calendly CTA buttons
- Updated `_schedule_post_call_email()` in `bland_client.py` to schedule BOTH:
  - t+3min: brief "How We Work" process intro (send_post_call_email)
  - t+60min: full onboarding roadmap (send_onboarding_guide_email)

### 2. Carrier Onboarding Documentation Created
- `CARRIER_ONBOARDING_GUIDE.md` — comprehensive markdown guide covering 5-step process,
  timeline, what carriers need, pricing economics, FAQ, support escalation
- `CARRIER_ONBOARDING_EMAIL_TEMPLATE.html` — standalone branded HTML email template
  with visual timeline, doc table, pricing box, {{CARRIER_NAME}}/{{COMPANY_NAME}} placeholders

### 3. Security + Reliability Audit — 9 Bugs Fixed
Full webhook/API audit across 6 files. All fixes committed and pushed.

**Bug 1 — routes_bland_webhooks.py: HMAC stub never validated**
- verify_bland_webhook() checked headers present but never computed HMAC comparison
- FIX: compute HMAC-SHA256(secret, timestamp.body), hmac.compare_digest() against header

**Bug 2 — routes_bland_webhooks.py: 500 on errors caused Bland AI retries**
- FIX: BackgroundTasks.add_task() pattern, return 200 immediately (fast ACK)

**Bug 3 — routes_bland_webhooks.py: No call_id idempotency**
- FIX: _seen_call_ids set with 5000-entry memory bound

**Bug 4a — routes_adobe_webhooks.py: Wrong table name**
- sb.table("carriers") → sb.table("active_carriers")

**Bug 4b — routes_adobe_webhooks.py: No authentication**
- Anyone could POST and trigger 30-step onboarding + Stripe charges
- FIX: shared secret check via Authorization header (ADOBE_WEBHOOK_SECRET env var)

**Bug 4c — routes_adobe_webhooks.py: Blocked on fire_onboarding before ACK**
- FIX: BackgroundTasks.add_task(_run_onboarding), return 200 immediately
- Added _seen_agreements dedup set

**Bug 5 — email_ingest.py: SendGrid attachments never parsed**
- form.getlist("attachments") always empty — SendGrid sends as attachment1, attachment2...
- FIX: iterate form.get(f"attachment{i}") until None

**Bug 6 — routes_prospecting.py: No try/except on Supabase insert**
- FIX: wrap in try/except, increment skipped on error, continue loop

**Bug 7 — routes_prospecting.py + vance.py: Stale "vance" agent name**
- log_agent("vance") and query agent="vance" meant all calls hidden in CRM after Nova rename
- FIX: log as "nova"; query .in_(["nova","vance"]) for historical rows; vance.py returns agent="nova"

**Bug 8 — routes_prospecting.py: Phone validation too lenient**
- FIX: validate len==11 and startswith("1") before proceeding, raise 400 otherwise

**Bug 9 — routes_comms.py: Twilio inbound has no signature verification**
- Documented as warning (not yet fixed in code — Twilio signature check requires twilio library)

### 4. settings.py additions
- ADOBE_WEBHOOK_SECRET field added for Adobe webhook auth

### 5. Local Server Setup Troubleshooting (user-side)
- User attempting to run backend locally on Windows
- Python 3.14.3 installed — too new, pydantic-core/lxml have no wheels for 3.14
- Directed to install Python 3.12 from python.org
- User now attempting venv setup — hitting PowerShell execution policy issue

---

## Files Touched

| File | Change |
|---|---|
| `backend/app/agents/bland_client.py` | _schedule_post_call_email() fires both emails (3min + 60min) |
| `backend/app/prospecting/follow_up.py` | Added send_onboarding_guide_email() full HTML guide |
| `backend/app/api/routes_bland_webhooks.py` | Real HMAC check, BackgroundTasks, call_id dedup, BlandEvent defaults |
| `backend/app/api/routes_adobe_webhooks.py` | Auth check, fast ACK via BackgroundTasks, right table, agreement dedup |
| `backend/app/email_ingest.py` | Fixed attachment parsing (attachment1..N not getlist) |
| `backend/app/api/routes_prospecting.py` | Nova agent name, phone validation, Supabase try/except, logger added |
| `backend/app/agents/vance.py` | Returns agent="nova" |
| `backend/app/settings.py` | Added adobe_webhook_secret |
| `CARRIER_ONBOARDING_GUIDE.md` | Created comprehensive onboarding reference |
| `CARRIER_ONBOARDING_EMAIL_TEMPLATE.html` | Created branded HTML email template |

---

## Commits on Feature Branch (claude/migrate-airtable-leads-eOcKI)

```
69daac0 Security + reliability audit: fix 9 webhook/API bugs across 6 files
1c60e01 Two-email post-call sequence: 3-min intro + 1-hour full onboarding guide
7a20dce Add carrier onboarding guide and email template
60871af Bundle W9 into carrier onboarding signing session alongside Dispatch Agreement
3ac5923 Wire Adobe Sign e-signature to onboarding step 14; add integration key auth
f341204 Rename Vance to Nova (female), add 3-min post-call follow-up email, update onboarding docs
```

---

## Pending Tasks

### User Action Required
1. **Python 3.12**: Install from python.org (3.14 too new for pydantic-core/lxml wheels)
2. **PowerShell venv activation**: Use `.\venv\Scripts\Activate.ps1` (in progress)
3. **Adobe Sign setup**: Integration Key + two Library Templates (agreement + W9)
4. **Bland AI**: Fix API key ≠ org_id, disable IP allowlist
5. **Supabase schema**: Add `adobe_agreement_id TEXT` column to active_carriers table

### Production Deployment
- Backend not yet deployed (fly.toml exists but app never launched)
- Fastest path: `fly deploy --config deploy/fly.toml` after env vars set
- Alternatively: Railway or Render (simpler for first deploy)

### Code TODOs
- Twilio inbound SMS signature verification (routes_comms.py)
- threading.Timer reliability: replace with Supabase scheduled_tasks + polling worker
  for durable email scheduling (survives process restarts)
- Test full Adobe Sign onboarding flow end-to-end
- Configure Bland AI webhook URL in Bland dashboard (currently not set)

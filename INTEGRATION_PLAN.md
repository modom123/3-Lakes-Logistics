# Driver App Full Integration Plan

## Phase 1: Supabase Setup (Database & Auth)
- [ ] Create Supabase tables: drivers, loads, driver_earnings, driver_messages, driver_documents, dispatchers
- [ ] Set up RLS policies (drivers see only their own data)
- [ ] Configure phone+PIN auth method (custom auth via backend)
- [ ] Configure Supabase client in driver app with real credentials

## Phase 2: Driver App Real Data Integration
- [ ] Replace demo auth with Supabase phone+PIN login
- [ ] Wire loadCurrentLoad() to query Supabase loads table
- [ ] Wire loadAvailableLoads() to fetch booked loads
- [ ] Wire loadMessages() to fetch real driver_messages
- [ ] Wire loadPayData() to calculate from driver_earnings
- [ ] Wire document upload to Supabase Storage
- [ ] Set up real-time subscriptions for instant updates

## Phase 3: Backend Integration (FastAPI)
- [ ] Deploy FastAPI backend to production (Fly.dev)
- [ ] Create `/api/driver-auth/login` endpoint (phone+PIN → Supabase)
- [ ] Create `/api/fleet` endpoints (loads queries)
- [ ] Create `/api/comms` endpoints (messages)
- [ ] Create `/api/earnings` endpoints (driver pay calculations)
- [ ] Wire backend to Supabase for all data

## Phase 4: Airtable Lead Migration
- [ ] Extract 100 leads from Airtable
- [ ] Create carriers table in Supabase
- [ ] Insert leads with onboarding status
- [ ] Wire intake form to create carrier record + trigger Adobe Sign

## Phase 5: Data Sync & Deployment
- [ ] Test end-to-end: form → Supabase → driver app
- [ ] Deploy driver app to Firebase Hosting (already done)
- [ ] Rebuild APK with updated backend URLs
- [ ] Deploy to Firebase App Distribution

---

## What We Have Now
✅ PWA deployed to Firebase Hosting with light theme + demo mode
✅ Layout matches user's mockups (5 pages, all visible)
✅ Login page with demo bypass

## What's Needed
1. Supabase project & tables
2. Supabase credentials (URL + anon key)
3. Deployed FastAPI backend
4. Airtable API access (already have)
5. Adobe Sign credentials (user has account)

---

**Estimated timeline**: 4-6 hours for full integration
**Start with**: Supabase setup + basic queries

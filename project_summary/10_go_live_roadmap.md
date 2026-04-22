# Go-Live Roadmap (Steps 1–150)

Everything needed to take the current branch from "code + docs" to
"paying customers, production, on-call". Grouped into 10 phases of 15
steps. Check off as you go.

Anything marked **[YOU]** requires human action outside the repo
(account creation, credentials, vendor dashboards, DNS). Everything
else is code/config that already exists in this repo or is a verifiable
command output.

---

## Phase A — Account provisioning (1–15)

1. **[YOU]** Register domain `3lakeslogistics.com` (or confirm existing ownership + login).
2. **[YOU]** Create Cloudflare account and add the domain; update registrar to Cloudflare nameservers.
3. **[YOU]** Create Supabase organization + production project (region: `us-east-1` or `us-central-1`). Save project ref + anon / service-role / JWT secret.
4. **[YOU]** Create Stripe account; complete business verification; enable live mode.
5. **[YOU]** Create Twilio account; buy one toll-free or 10DLC number; complete A2P brand + campaign registration.
6. **[YOU]** Create Vapi.ai account; buy one phone number; create an outbound assistant named "Vance" with a base prompt.
7. **[YOU]** Create Motive developer account; request an ELD API key; save webhook secret.
8. **[YOU]** Register for an FMCSA WebKey (free — `mobile.fmcsa.dot.gov`).
9. **[YOU]** Create Google Cloud project; enable Maps JavaScript / Directions / Geocoding APIs; create a restricted API key.
10. **[YOU]** Create Resend account (or Postmark); verify `3lakeslogistics.com` as a sending domain; add SPF / DKIM / DMARC records in Cloudflare.
11. **[YOU]** Create Sentry account; create `3lakes-backend` project; save DSN.
12. **[YOU]** Create Slack workspace (or reuse); create `#ops` and `#alerts` channels; generate two Incoming Webhook URLs.
13. **[YOU]** Create Fly.io account; install `flyctl`; `fly auth login`.
14. **[YOU]** Create Airtable account and base (optional — only if legacy lead import is needed).
15. **[YOU]** Decide on a 1Password / Bitwarden / Doppler vault for durable secret storage. Put every credential from steps 1–14 in it. **Never email keys.**

---

## Phase B — Supabase schema + storage (16–30)

16. In Supabase dashboard → Settings → Database, copy the Postgres connection URI (direct, not pooler).
17. Local shell: `export SUPA_URL='postgresql://postgres:…/postgres'`.
18. Run `psql "$SUPA_URL" -c "select version();"` — confirm connectivity.
19. Run migrations 001–013 in order via the `for f in sql/0*.sql; do psql "$SUPA_URL" -f "$f"; done` loop from `docs/DEPLOY_FLY.md §3`.
20. In SQL editor, `select count(*) from founders_inventory;` — expect 8 rows.
21. `select category, total, claimed, reserved from founders_inventory;` — confirm 1,000 total, 0 claimed.
22. In Storage → New bucket → name `agreements`, **private**.
23. In Storage → Policies, add a service-role-only insert/select policy on `agreements`.
24. In Authentication → Providers, enable Email (magic link) and optionally Google.
25. In Authentication → URL Configuration, set Site URL to the production domain and add redirect URLs for the ops suite.
26. In SQL editor, run `select * from public.is_admin();` — should return false (you're not admin yet).
27. Create a first admin user in Authentication → Users; in SQL: `insert into carrier_user_map (user_id, carrier_id, role) values ('<uid>', null, 'admin');` (adjust schema if carrier_id is not nullable — add the row after onboarding instead).
28. Create two carrier-portal test users (one owner, one dispatcher) for later end-to-end testing.
29. Verify RLS: open the Supabase SQL editor with a JWT-simulated role and run `select * from leads;` — must return 0 rows for a non-admin.
30. Enable Point-in-Time Recovery (PITR) in Supabase Pro; set retention to 7 days minimum.

---

## Phase C — Encryption keys + Stripe products (31–45)

31. Generate the PII key: `python -c 'import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'`. Store in the vault as `PII_ENCRYPTION_KEY`.
32. Generate the API bearer: `python -c 'import secrets;print(secrets.token_urlsafe(48))'`. Store as `API_BEARER_TOKEN`.
33. In Stripe dashboard → Products, create "3 Lakes Founders" — $200/mo recurring. Save the price ID as `STRIPE_PRICE_FOUNDERS`.
34. Create "3 Lakes Pro" — $400/mo. Save `STRIPE_PRICE_PRO`.
35. Create "3 Lakes Scale" — $800/mo (or your chosen tier). Save `STRIPE_PRICE_SCALE`.
36. In Stripe → Developers → API keys, copy the live Secret key → `STRIPE_SECRET_KEY`.
37. In Stripe → Developers → Webhooks, create an endpoint `https://api.3lakeslogistics.com/api/webhooks/stripe` (you'll register it after deploy). For now save its signing secret as `STRIPE_WEBHOOK_SECRET`.
38. Sub­scribe the Stripe endpoint to: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_succeeded`, `invoice.payment_failed`.
39. In Twilio → Messaging → Services, create a service, attach the number, and get the service SID.
40. In Vapi → Assistants, note the Vance assistant ID → `VAPI_ASSISTANT_ID_VANCE`.
41. In Vapi → Phone Numbers, note the phone number ID → `VAPI_PHONE_NUMBER_ID`.
42. In Vapi → API Keys, create a key → `VAPI_API_KEY`; set a webhook secret → `VAPI_WEBHOOK_SECRET`.
43. In Motive → Settings → API, create an API key → `MOTIVE_API_KEY`; in Webhooks, set signing secret → `MOTIVE_WEBHOOK_SECRET`.
44. In Resend → API Keys, create a key → `RESEND_API_KEY`.
45. Copy `.env.example` → `.env.prod`; fill every value from phases A–C.

---

## Phase D — First Fly.io deploy (46–60)

46. `cd backend && fly launch --no-deploy --copy-config --name 3lakes-backend --region ord`.
47. Decline Fly's offer to create a Postgres/Upstash DB (Supabase owns data).
48. `git diff backend/fly.toml` — confirm Fly didn't overwrite the committed config.
49. Run `./scripts/fly_secrets_template.sh .env.prod` to push every secret in one call.
50. `fly secrets list` — verify every expected key is present.
51. `fly deploy` — watch for the "3 Lakes Logistics API ready" log line.
52. `fly status` — confirm three process types (api/worker/scheduler) are "started".
53. `fly scale count api=2 worker=2 scheduler=1`.
54. Confirm scheduler is singleton: `fly scale show scheduler` — count must be 1.
55. Smoke: `curl https://3lakes-backend.fly.dev/api/health` → `{"ok": true}`.
56. Smoke: `curl https://3lakes-backend.fly.dev/api/ready` → `{"ready": true}`. If false, check Supabase connectivity from logs.
57. `fly logs -i <scheduler-machine-id>` — watch for "scheduler started with 10 jobs".
58. `fly logs -i <worker-machine-id>` — watch for "worker ready" line.
59. Test an agent end-to-end: `curl -H "Authorization: Bearer $API_BEARER_TOKEN" -X POST https://3lakes-backend.fly.dev/api/agents/pulse/run -d '{"kind":"kpi_snapshot"}'` → expect `status: "ok"`.
60. In Supabase, `select * from agent_runs order by started_at desc limit 5;` — confirm the run was audited.

---

## Phase E — Domain, TLS, CORS (61–75)

61. `fly certs add api.3lakeslogistics.com`.
62. In Cloudflare DNS, add the CNAME Fly tells you to. **Set proxy to "DNS only" (grey cloud)** — Fly handles TLS.
63. `fly certs show api.3lakeslogistics.com` — wait until status is "Issued" (usually < 5 min).
64. `curl https://api.3lakeslogistics.com/api/health` — confirm the custom domain serves.
65. Update secrets: `fly secrets set CORS_ORIGINS='https://3lakeslogistics.com,https://ops.3lakeslogistics.com'`.
66. In Cloudflare Pages, create project `3lakes-public` pointing at the GitHub repo's `main` branch (or upload the repo once).
67. Set the Pages build output directory to the repo root (or move the HTML files under `/public/` first).
68. In each HTML file, ensure `window.__3LL_API_BASE = 'https://api.3lakeslogistics.com'` is set. Commit if you hardcode it.
69. Add DNS `CNAME @` (or alias) → `3lakes-public.pages.dev`.
70. Add DNS `CNAME ops` → Pages project for the Ops Suite (separate project or same with routing).
71. Verify `https://3lakeslogistics.com` serves `index (7).html` and loads without mixed-content warnings.
72. Verify `https://ops.3lakeslogistics.com` serves the command center.
73. In the Ops Suite, in browser console: `localStorage.setItem('3LL_API_TOKEN','<API_BEARER_TOKEN>')`; reload — KPI tiles must populate.
74. From the public site's browser console, `fetch('/api/founders/inventory')` — confirm live counter.
75. Hit `/api/dashboard/kpis` from a non-authed tab — must return 401.

---

## Phase F — Webhook registration + verification (76–90)

76. In Stripe → Webhooks, set endpoint URL to `https://api.3lakeslogistics.com/api/webhooks/stripe`.
77. Stripe dashboard → "Send test event" → `invoice.payment_succeeded`. Then in Supabase: `select * from webhook_log where source='stripe' order by created_at desc limit 1;` — must show `verified=true`.
78. Confirm `stripe_events` has the event row (idempotency check).
79. In Vapi → Server URL, set to `https://api.3lakeslogistics.com/api/webhooks/vapi`.
80. Send a test call event from Vapi; verify `webhook_log.verified=true`.
81. In Motive → Webhooks, set URL to `https://api.3lakeslogistics.com/api/webhooks/motive`, pick `vehicle.position` + `driver.hos_status` events.
82. Trigger a Motive test webhook; verify `truck_telemetry` grows by one row.
83. In Twilio → Messaging service → Incoming webhook, set to `https://api.3lakeslogistics.com/api/webhooks/twilio/sms`.
84. Send an SMS from your phone → the Twilio number; check `sms_log` has an inbound row and an opt-out test (text "STOP") creates an `sms_opt_out` row.
85. Confirm a reply came back (Echo auto-reply) within 5 s.
86. Confirm any failed signature lands in `webhook_log` with `verified=false` and the API returns 400 — test by pushing a webhook with a bad signature.
87. Enable "Signed Webhooks" enforcement in every vendor dashboard that supports it.
88. In Fly, set `fly secrets set STRIPE_WEBHOOK_SECRET=<live value>` if it was a test value in Phase C.
89. Rotate `API_BEARER_TOKEN` to a new value; update it in the Ops Suite's `localStorage`; redeploy.
90. Document the final webhook URLs in `docs/RUNBOOK.md`'s on-call table.

---

## Phase G — End-to-end smoke tests (91–105)

91. **Intake happy path:** from the public site, fill out all 6 steps with test data + a Stripe test card (`4242 4242 4242 4242`). Form should redirect to Stripe Checkout.
92. Complete checkout. Confirm `active_carriers.status='active'`, `subscription_status='active'`, `stripe_subscription_id` populated.
93. Confirm `signatures_audit` has a row with a `pdf_url` pointing to the `agreements` bucket.
94. Download the PDF from the signed URL — contents match what was signed.
95. Confirm `founders_inventory.claimed` for the chosen category incremented by 1.
96. Confirm `insurance_compliance.safety_light` populated (Shield ran).
97. Confirm at least one `agent_log` row for `shield` with the new `carrier_id`.
98. **Payment failure path:** in Stripe dashboard, simulate a failed invoice; confirm `active_carriers.status='suspended'` and a dunning email sent (check Resend dashboard).
99. **Cancel path:** cancel the subscription in Stripe; confirm `active_carriers.status='churned'`.
100. **Agent manual run:** from the Ops Suite → AI Agents page, click "Run" on Pulse. Expect a JSON response and a new `agent_runs` row.
101. **Queue smoke:** `curl … /api/agents/sonny/run -d '{"kind":"match_all_trucks"}'` — confirm no matches yet (expected — no trucks seeded), status ok.
102. **Telemetry smoke:** POST a fake Motive payload; confirm `truck_telemetry` row and Ops Suite fleet map page shows the point.
103. **Founders reserve/claim:** call `POST /api/founders/reserve` with a UUID; then `POST /api/founders/claim` with the same UUID → reserved→claimed transition, `claimed` increments.
104. **SMS round-trip:** text the Twilio number "PAY" — expect Echo's auto-reply.
105. **Daily digest dry-run:** manually trigger Pulse: `POST /api/agents/pulse/run -d '{"kind":"daily_digest"}'` — confirm a message lands in `#ops` Slack.

---

## Phase H — Auth UX for carriers + dispatchers (106–120)

106. In the Ops Suite HTML, replace the `localStorage.getItem('3LL_API_TOKEN')` bearer with a Supabase Auth JWT: add the Supabase JS client and a sign-in form.
107. Add a sign-out button that clears the JWT from storage.
108. Add a session refresh hook (the Supabase client handles this automatically; verify it's wired).
109. On sign-in, call `/api/auth/bootstrap` (new endpoint — returns carrier_id + role from `carrier_user_map`); redirect accordingly.
110. Add a carrier-admin portal page at `/portal` on the public site that requires a carrier-scoped JWT — shows plan, last invoice, COI expiry, drivers.
111. Wire "Add Driver" action from the portal to a new `POST /api/drivers/` endpoint that inserts into `drivers` scoped by JWT.
112. Wire "Update COI" — accepts a PDF upload, Audit agent OCRs it, updates `insurance_compliance.policy_expiry`.
113. Add a driver-facing PWA stub (can be a single HTML page) with phone login, showing current load + HOS from `driver_hos_status`.
114. Publish the PWA manifest + service worker so it's installable on iOS/Android.
115. Wire "Accept load" in the driver PWA → updates `load_matches.status='booked'` and triggers Atlas transition.
116. Add driver push notifications via a service worker + Fly-side web push (or Expo/Firebase if native).
117. Add a "Download my settlement" link in the driver PWA that fetches the signed PDF from Supabase Storage.
118. Add a role-switching UI in the Ops Suite (admin vs. dispatcher) so the same login covers both surfaces.
119. Add MFA-optional in Supabase Auth for admin users.
120. Rate-limit auth endpoints at Fly edge (or via Cloudflare) — block brute force.

---

## Phase I — Observability + hardening (121–135)

121. Create Sentry alerts: email on any `error` level event; PagerDuty on 5+ errors/min.
122. Create Slack alerts via Sentry's Slack integration to `#alerts`.
123. Set up a Cloudflare Page Rule caching the static HTML for 1 h with cache-busting via a query-string version.
124. Add Cloudflare Analytics to measure uptime + p95 latency against `api.3lakeslogistics.com/api/health`.
125. Enable Fly Metrics Grafana dashboard; pin the `3lakes-backend` app.
126. Configure a scheduled Supabase logical backup export to S3 or Cloudflare R2 (nightly).
127. Document disaster recovery: time-to-restore from Supabase PITR + Storage re-upload scenario.
128. Run a **chaos drill**: kill a worker machine mid-task — confirm the task re-runs and the eventual run succeeds.
129. Run a **load test** with `hey` or `k6`: 200 req/s to `/api/health` and `/api/founders/inventory` for 5 min. Watch latency + Fly auto-scaling.
130. Tune `queue_max_concurrency` based on queue depth observed in load test.
131. Add database indexes where the query analyzer shows sequential scans (Supabase → Reports → Query Performance).
132. Verify the retention purge job runs and doesn't delete anything in its dry-run mode first (flip to real mode once confirmed).
133. Rotate `PII_ENCRYPTION_KEY` plan: document the dual-key re-encryption procedure in RUNBOOK.md.
134. Security review: run `pip-audit` and `bandit app/` in CI; fix any medium+ findings.
135. Run an OWASP ZAP scan against the public site + api; patch any high findings.

---

## Phase J — Launch + first 10 carriers (136–150)

136. Gate production behind an invite code in the intake form: add `invite_code` field; reject unknown codes.
137. Generate 10 invite codes and distribute to pilot carriers.
138. Stand up a `#pilot` Slack channel; invite pilot carriers via their preferred channel.
139. Schedule a 15-minute onboarding call for each pilot; screen-share the intake form.
140. For each pilot carrier, verify end-to-end: intake → Stripe → activation → Motive connection → first load match.
141. After each pilot, post a retrospective thread with bug reports and feature requests; triage daily.
142. Fix the top-3 rough edges from the first 5 pilots before onboarding the next 5.
143. Add a status page (statuspage.io or a static page driven by `/api/health`) — link it from the site footer.
144. Publish the first weekly operations report to pilots: loads moved, miles driven, gross revenue.
145. Remove the invite gate once the system has been stable for 30 days.
146. Announce public availability in email + LinkedIn + Slack; throttle intake to 10/day to control support load.
147. Staff the on-call rotation (or confirm the Commander is primary); publish the on-call schedule in `#ops`.
148. Set monthly cadence: FMCSA scrape volume, email deliverability, Stripe MRR, Founders slots remaining.
149. Quarter-end review: Founders 1,000 remaining? What percent of claimed slots are still active? Where is churn coming from?
150. Ship v1.0 — cut a git tag `v1.0`, update `project_summary/01_overview.md` to reflect the live product, and celebrate.

---

## Gate criteria

| Phase | Gate |
|-------|------|
| A–C | All credentials stored in vault; migrations apply cleanly to a throw-away Supabase project first |
| D | `fly status` all green; `/api/ready` returns `{ready:true}` |
| E | TLS cert issued; Ops Suite loads real KPI data |
| F | Every webhook produces a `verified=true` row; bad signatures produce `verified=false` and HTTP 400 |
| G | Full intake → Stripe → active transition completes for a test carrier |
| H | A non-admin carrier can sign in, view their data, and cannot see any other carrier's data (RLS check) |
| I | Load test passes; Sentry catches a deliberately-induced error |
| J | 10 pilots onboarded with <2 critical bugs per pilot |

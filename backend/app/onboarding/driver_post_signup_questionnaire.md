# 3 Lakes Light Fleet — Post-Signup Questionnaire

Sent as a follow-up to the welcome email (after `send_welcome_email` /
`step2_welcome_email` in `maya_welcome.py`, before or alongside the Day 1 SMS
and Day 2 email). Goal: confirm readiness, learn availability/preferences, and
surface anything that needs a human before the first trip is dispatched.

---

## 1. Confirm Your Details
1. Is the name and phone number on file correct? *(Yes / No — if No, please provide correction)*
2. What's the best email address to reach you at?
3. What city/area will you primarily be operating in?

## 2. Vehicle & Equipment Readiness
4. What vehicle will you be using? *(Year / Make / Model)*
5. Is your vehicle currently insured, registered, and under 10 years old?  *(Yes / No)*
6. Do you have a smartphone with data service to run the driver app and partner platform apps? *(Yes / No)*
7. Any known vehicle issues we should be aware of before your first trip? *(open text)*

## 3. Approved Services — Confirm & Prioritize
8. You were approved for: **{{approved_services}}**. Does this match what you signed up for? *(Yes / No)*
9. If approved for more than one service, which would you like to receive trips for first? *(rank or select primary)*
   - Medical Transport (NEMT)
   - Executive Transfers
   - Same-Day Courier
   - Gig / On-Demand
10. Do you have prior experience in any of these service types? *(open text — e.g. rideshare, courier, NEMT, chauffeur)*

## 4. Platform & App Setup
11. Have you downloaded the app(s) for your approved service(s) (Curri, Roadie, Modivcare, MTM, Uber/Lyft Business, 3 Lakes Driver Portal)? *(Yes, all / Some / Not yet)*
12. If "Some" or "Not yet" — which app(s) do you still need help setting up? *(checklist)*
13. Have you set up direct deposit / your payout method in the Driver Portal? *(Yes / No / Need help)*

## 5. Availability & Scheduling
14. What days are you generally available? *(Mon–Sun checklist)*
15. What time blocks work best for you? *(Early AM / Daytime / Evening / Overnight / Flexible)*
16. Roughly how many trips per week are you hoping to run?
17. Is this full-time, part-time, or occasional/gig work for you?

## 6. Support & Training Needs
18. Do you have questions about how dispatch, trip acceptance, or pay works? *(Yes / No — if Yes, open text)*
19. Would you like a live walkthrough call with your onboarding coordinator before your first trip? *(Yes / No)*
20. Is there anything blocking you from accepting your first trip right now? *(open text)*

## 7. Communication Preferences
21. How do you prefer to be contacted for dispatch and updates? *(Text / Call / Email / App notification)*
22. Are you okay receiving occasional promotional or bonus-tier updates via SMS? *(Yes / No)*

## 8. Feedback
23. How did you hear about 3 Lakes Light Fleet? *(open text / referral name)*
24. On a scale of 1–5, how clear was the sign-up and welcome process so far?
25. Anything else we should know before your first assignment? *(open text)*

---

### Notes for implementation (when ready to wire this up)
- Fields in `{{double braces}}` should be templated from the driver record
  (`light_vehicle_drivers`), same pattern used in `welcome_packet.py` /
  `maya_welcome.py`.
- Natural insertion point: a new scheduled step between `step2_welcome_email`
  and `step3_welcome_call` in `run_welcome_workflow()`, so answers (esp. #8,
  #14–17, #19–20) can be fed into Maya's welcome call script.
- Responses could land in a new `driver_intake_responses` table keyed by
  `driver_id`, mirroring how `insurance_compliance` / `banking_accounts` are
  keyed off `carrier_id` elsewhere in the codebase.

-- 026_reset_unverified_active_lf_drivers.sql
-- Data correction: light-fleet drivers that were auto-activated by the old
-- honor-system intake path (status='active' while never actually verified) must
-- not be treated as active. A driver is only active/onboarded once BOTH required
-- steps are complete: identity/MVR verification AND a connected payout account.
--
-- Return any LF driver that is 'active' but whose MVR was never cleared to the
-- onboarding pipeline (status='inactive'). Verified drivers are left untouched;
-- the dashboard separately keeps verified-but-not-yet-paid drivers in the
-- onboarding view until their Stripe payout account is connected.
--
-- Idempotent: safe to run more than once.

update public.light_vehicle_drivers
   set status = 'inactive'
 where status = 'active'
   and coalesce(mvr_status, 'pending') <> 'clear';

-- Also clear a premature onboarded_at stamp for those same drivers so nothing
-- downstream reads them as "onboarding complete".
update public.light_vehicle_drivers
   set onboarded_at = null
 where status = 'inactive'
   and coalesce(mvr_status, 'pending') <> 'clear'
   and onboarded_at is not null;

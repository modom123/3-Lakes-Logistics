-- Stage 5 steps 86 + 69: Twilio SMS log, opt-out ledger, nurture enrollments.
create table if not exists public.sms_log (
  id          uuid primary key default gen_random_uuid(),
  direction   text not null,          -- in | out
  phone       text not null,
  body        text,
  provider_sid text,
  carrier_id  uuid references public.active_carriers(id) on delete set null,
  created_at  timestamptz not null default now()
);
create index if not exists sms_log_phone_idx on public.sms_log (phone, created_at desc);

create table if not exists public.sms_opt_out (
  phone      text primary key,
  reason     text,
  created_at timestamptz not null default now()
);

create table if not exists public.nurture_enrollments (
  id           uuid primary key default gen_random_uuid(),
  lead_id      uuid,
  carrier_id   uuid references public.active_carriers(id) on delete set null,
  channel      text not null default 'email',  -- email | sms
  to_address   text not null,
  template_key text,
  subject      text,
  body         text,
  step_index   int  not null default 0,
  status       text not null default 'active',  -- active | paused | done | failed
  next_send_at timestamptz not null default now(),
  last_sent_at timestamptz,
  created_at   timestamptz not null default now()
);
create index if not exists nurture_due_idx
  on public.nurture_enrollments (next_send_at) where status = 'active';

alter table public.sms_log enable row level security;
alter table public.sms_opt_out enable row level security;
alter table public.nurture_enrollments enable row level security;
create policy sms_log_admin on public.sms_log      for select using (public.is_admin());
create policy sms_opt_admin on public.sms_opt_out  for select using (public.is_admin());
create policy nurture_admin on public.nurture_enrollments for select using (public.is_admin());

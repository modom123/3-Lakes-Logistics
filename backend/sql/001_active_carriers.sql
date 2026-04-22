-- Step 5: active_carriers — Master Hub row per subscribed carrier.
-- Created by POST /api/carriers/intake (the 6-step form in index (7).html).

create extension if not exists "pgcrypto";

create table if not exists public.active_carriers (
  id              uuid primary key default gen_random_uuid(),
  company_name    text not null,
  legal_entity    text,
  dot_number      text unique,
  mc_number       text unique,
  ein             text,
  phone           text,
  email           text,
  address         text,
  years_in_business int,

  -- subscription (Penny)
  plan            text not null default 'founders',
  stripe_customer_id     text,
  stripe_subscription_id text,
  subscription_status    text default 'pending',

  -- e-sign (Signature workflow)
  esign_name      text,
  esign_ip        text,
  esign_user_agent text,
  esign_timestamp timestamptz,
  agreement_pdf_hash text,

  -- lifecycle
  status          text not null default 'onboarding',
    -- values: onboarding | active | suspended | churned
  onboarded_at    timestamptz,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists idx_carriers_dot on public.active_carriers(dot_number);
create index if not exists idx_carriers_mc on public.active_carriers(mc_number);
create index if not exists idx_carriers_status on public.active_carriers(status);

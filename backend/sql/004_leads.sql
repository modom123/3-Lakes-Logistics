-- Step 7: leads — prospecting pipeline. Populated by FMCSA scraper,
-- Google Maps scraper, DAT/Truckstop scraper, Airtable sync.

create table if not exists public.leads (
  id              uuid primary key default gen_random_uuid(),
  source          text not null,  -- fmcsa | gmaps | dat | truckstop | truckpaper | airtable | referral | social
  source_ref      text,            -- external id from the source system
  company_name    text,
  dot_number      text,
  mc_number       text,
  contact_name    text,
  contact_title   text,
  phone           text,
  email           text,
  address         text,
  fleet_size      int,
  equipment_types text[],

  score           int,             -- 1-10 (Vance lead-score algo)
  stage           text default 'new',
    -- new | contacted | engaged | qualified | converted | nurture | dead
  owner_agent     text,            -- vance | echo | nova
  last_touch_at   timestamptz,
  next_touch_at   timestamptz,
  do_not_contact  boolean default false,

  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create unique index if not exists idx_leads_dot on public.leads(dot_number) where dot_number is not null;
create unique index if not exists idx_leads_mc  on public.leads(mc_number)  where mc_number  is not null;
create index if not exists idx_leads_stage on public.leads(stage);
create index if not exists idx_leads_score on public.leads(score desc);
create index if not exists idx_leads_next_touch on public.leads(next_touch_at) where do_not_contact = false;

-- ============================================================
-- Migration 020: Customer / Shipper CRM
-- Creates a normalized customers table so dispatchers can track
-- shipper and broker relationships, load history, and payment terms.
-- ============================================================

create table if not exists public.customers (
  id              uuid primary key default gen_random_uuid(),
  company_name    text not null,
  contact_name    text,
  email           text,
  phone           text,
  address         text,
  city            text,
  state           text,
  zip             text,
  -- shipper = ships freight with us; broker = gives us loads; both = both
  customer_type   text not null default 'broker',
  payment_terms   text not null default 'net30',   -- net15, net30, net45, quick_pay
  credit_limit    numeric(10,2),
  credit_rating   text,                             -- A, B, C, D
  mc_number       text,
  dot_number      text,
  notes           text,
  status          text not null default 'active',   -- active, inactive, suspended
  -- cached aggregates (refreshed on load save)
  total_loads     int not null default 0,
  total_revenue   numeric(12,2) not null default 0,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists idx_customers_name   on public.customers(company_name);
create index if not exists idx_customers_type   on public.customers(customer_type);
create index if not exists idx_customers_status on public.customers(status);
create index if not exists idx_customers_email  on public.customers(email);

-- Link loads to customers
alter table public.loads add column if not exists customer_id uuid references public.customers(id);
create index if not exists idx_loads_customer on public.loads(customer_id) where customer_id is not null;

-- Auto-update updated_at
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;

drop trigger if exists trg_customers_updated_at on public.customers;
create trigger trg_customers_updated_at
  before update on public.customers
  for each row execute function public.set_updated_at();

-- Refresh cached totals when a load is inserted/updated
create or replace function public.refresh_customer_totals()
returns trigger language plpgsql security definer as $$
declare cid uuid := coalesce(NEW.customer_id, OLD.customer_id);
begin
  if cid is null then return coalesce(NEW, OLD); end if;
  update public.customers
  set
    total_loads   = (select count(*)              from public.loads where customer_id = cid),
    total_revenue = (select coalesce(sum(rate_total::numeric), 0) from public.loads where customer_id = cid)
  where id = cid;
  return coalesce(NEW, OLD);
end;
$$;

drop trigger if exists trg_loads_customer_totals on public.loads;
create trigger trg_loads_customer_totals
  after insert or update or delete on public.loads
  for each row execute function public.refresh_customer_totals();

-- Invoices table — billing records for carriers
-- Relates to loads via load_id, carriers via carrier_id

create table if not exists public.invoices (
  id              uuid primary key default gen_random_uuid(),
  carrier_id      uuid not null references public.active_carriers(id) on delete cascade,
  load_id         uuid references public.loads(id) on delete set null,

  -- Invoice details
  invoice_number  text,
  amount          decimal(12,2) not null default 0,
  description     text,

  -- Dates
  issued_at       timestamptz not null default now(),
  due_date        date not null,
  paid_at         timestamptz,

  -- Status tracking
  status          text not null default 'unpaid',
    -- unpaid | paid | overdue | cancelled
  payment_method  text,  -- stripe_transfer | bank_transfer | check | cash
  notes           text,

  -- Tracking
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),

  unique(carrier_id, load_id, invoice_number)
);

create index if not exists idx_invoices_carrier on public.invoices(carrier_id);
create index if not exists idx_invoices_status on public.invoices(status);
create index if not exists idx_invoices_due_date on public.invoices(due_date);
create index if not exists idx_invoices_load on public.invoices(load_id);
create index if not exists idx_invoices_issued on public.invoices(issued_at desc);

-- View: days_overdue calculated field
create or replace view public.invoices_with_aging as
select
  i.*,
  case
    when i.status = 'paid' then 0
    when i.status = 'overdue' then (current_date - i.due_date)
    when i.status = 'unpaid' and current_date > i.due_date then (current_date - i.due_date)
    else 0
  end as days_overdue,
  case
    when i.status = 'paid' then 'paid'
    when current_date > i.due_date and i.status != 'paid' then 'overdue'
    else i.status
  end as current_status
from public.invoices i;

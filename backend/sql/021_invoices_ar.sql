-- ============================================================
-- Migration 021: Invoicing + AR Tracking enhancements
-- Adds customer linkage, payment terms, invoice date, and a
-- dedicated aging view so Eagle Eye can show 0-30/31-60/61-90/90+
-- ============================================================

-- Link invoices to the new customers CRM table
alter table public.invoices add column if not exists customer_id    uuid references public.customers(id);
alter table public.invoices add column if not exists invoice_date   date not null default current_date;
alter table public.invoices add column if not exists payment_terms  text not null default 'net30';
alter table public.invoices add column if not exists notes          text;
alter table public.invoices add column if not exists sent_at        timestamptz;  -- when emailed to customer
alter table public.invoices add column if not exists sent_to        text;         -- email address

-- Index for AR queries
create index if not exists idx_invoices_customer  on public.invoices(customer_id) where customer_id is not null;
create index if not exists idx_invoices_due_date  on public.invoices(due_date) where status <> 'Paid';
create index if not exists idx_invoices_created   on public.invoices(created_at desc);

-- Auto-mark overdue: invoices past due_date and still Unpaid → Overdue
-- (run as a cron or call manually; also triggers on read in the API)
create or replace function public.refresh_overdue_invoices()
returns void language plpgsql security definer as $$
begin
  update public.invoices
  set status = 'Overdue'
  where status = 'Unpaid'
    and due_date < current_date;
end;
$$;

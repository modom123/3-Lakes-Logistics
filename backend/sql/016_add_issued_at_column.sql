-- Add issued_at column to invoices table
-- This column tracks when an invoice was officially issued to the customer

alter table public.invoices
  add column if not exists issued_at timestamptz not null default created_at;

-- Create index on issued_at for faster queries
create index if not exists idx_invoices_issued_at on public.invoices(issued_at desc);

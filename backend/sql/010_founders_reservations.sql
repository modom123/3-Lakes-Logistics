-- Stage 5 step 77: Founders reservations (idempotent reserve→pay→claim).
create table if not exists public.founders_reservations (
  id          text primary key,           -- client-supplied idempotency key (uuid)
  category    text not null references public.founders_inventory(category) on delete restrict,
  carrier_id  uuid references public.active_carriers(id) on delete set null,
  email       text,
  status      text not null default 'reserved',  -- reserved | claimed | released | expired
  expires_at  timestamptz,
  claimed_at  timestamptz,
  created_at  timestamptz not null default now()
);
create index if not exists founders_rsv_status_idx on public.founders_reservations (status, expires_at);

alter table public.founders_inventory
  add column if not exists reserved int not null default 0;

alter table public.founders_reservations enable row level security;
create policy rsv_admin on public.founders_reservations for select using (public.is_admin());

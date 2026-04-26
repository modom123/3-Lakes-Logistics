-- Contract Lifecycle Management tables
create table if not exists contracts (
  id                  uuid primary key default gen_random_uuid(),
  carrier_id          uuid references active_carriers(id),
  contract_type       text not null,
  -- draft | active | executed | expired | disputed | terminated
  status              text not null default 'draft',

  -- raw document
  document_url        text,
  raw_text            text,

  -- AI-extracted digital twin (100+ variables)
  extracted_vars      jsonb not null default '{}',

  -- promoted fields for fast querying
  counterparty_name   text,
  rate_total          numeric(10,2),
  rate_per_mile       numeric(6,4),
  origin_city         text,
  destination_city    text,
  pickup_date         date,
  delivery_date       date,
  payment_terms       text,

  -- lifecycle
  signed_at           timestamptz,
  expires_at          timestamptz,
  milestone_pct       int not null default 0,

  -- accounting linkage
  invoice_id          uuid,
  gl_posted           boolean not null default false,
  revenue_recognized  boolean not null default false,

  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists idx_contracts_carrier        on contracts(carrier_id);
create index if not exists idx_contracts_status         on contracts(status);
create index if not exists idx_contracts_type           on contracts(contract_type);
create index if not exists idx_contracts_pickup_date    on contracts(pickup_date);
create index if not exists idx_contracts_extracted_vars on contracts using gin(extracted_vars);

-- Immutable audit trail for every contract state change
create table if not exists contract_events (
  id           uuid primary key default gen_random_uuid(),
  contract_id  uuid not null references contracts(id),
  event_type   text not null,
  actor        text,
  payload      jsonb not null default '{}',
  notes        text,
  created_at   timestamptz not null default now()
);

create index if not exists idx_contract_events_contract on contract_events(contract_id);
create index if not exists idx_contract_events_type     on contract_events(event_type);

-- Document vault: metadata for every PDF stored in Supabase Storage
create table if not exists document_vault (
  id           uuid primary key default gen_random_uuid(),
  carrier_id   uuid references active_carriers(id),
  contract_id  uuid references contracts(id),
  -- rate_conf | bol | pod | insurance | w9 | mc_authority | broker_agreement
  doc_type     text not null,
  filename     text not null,
  storage_path text not null,
  file_size_kb int,
  mime_type    text,
  -- pending | scanning | complete | failed
  scan_status  text not null default 'pending',
  scan_result  jsonb not null default '{}',
  uploaded_at  timestamptz not null default now()
);

create index if not exists idx_document_vault_carrier on document_vault(carrier_id);
create index if not exists idx_document_vault_type    on document_vault(doc_type);
create index if not exists idx_document_vault_scan    on document_vault(scan_status);

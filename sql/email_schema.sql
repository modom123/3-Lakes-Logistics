-- ============================================================
-- Email Ingest Pipeline Schema
-- Receives broker rate confirmations via SendGrid webhook,
-- extracts PDFs, runs OCR + CLM scanner, creates load records
-- ============================================================

-- email_log table — audit trail of all inbound emails
CREATE TABLE IF NOT EXISTS email_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_email text NOT NULL,
    to_email text NOT NULL,
    subject text,
    body_text text,
    body_html text,
    attachment_count int DEFAULT 0,
    status text DEFAULT 'received',  -- 'received','processing','load_created','low_confidence','error','archived'
    confidence numeric,
    extracted_data jsonb,  -- full CLM extraction results
    source text DEFAULT 'sendgrid',
    broker_name text,
    load_id uuid REFERENCES loads(id) ON DELETE SET NULL,
    notes text,
    received_at timestamptz DEFAULT now(),
    processed_at timestamptz,
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_email_log_status ON email_log(status);
CREATE INDEX IF NOT EXISTS idx_email_log_broker ON email_log(broker_name);
CREATE INDEX IF NOT EXISTS idx_email_log_load ON email_log(load_id);
CREATE INDEX IF NOT EXISTS idx_email_log_received ON email_log(received_at DESC);

ALTER TABLE email_log ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Only authenticated users can read email logs
CREATE POLICY email_log_read_policy ON email_log FOR SELECT
  USING (auth.role() = 'authenticated');

-- email_templates table — managed email templates for dispatch, confirmations, payouts
CREATE TABLE IF NOT EXISTS email_templates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    subject text NOT NULL,
    body_html text NOT NULL,
    body_text text,
    variables text[],  -- e.g. ['driver_name', 'load_number', 'pickup_address']
    usage_count int DEFAULT 0,
    last_used_at timestamptz,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Seed default email templates
INSERT INTO email_templates (name, subject, body_html, body_text, variables) VALUES
(
    'dispatch_sheet',
    'Load {{load_number}} — {{origin_city}} to {{dest_city}}',
    '<html><body><h2>Load Accepted</h2><p><strong>Driver:</strong> {{driver_name}}</p><p><strong>Load Number:</strong> {{load_number}}</p><p><strong>Route:</strong> {{origin_city}}, {{origin_state}} to {{dest_city}}, {{dest_state}}</p><p><strong>Rate:</strong> ${{rate_total}}</p><p><strong>Pickup:</strong> {{pickup_address}} at {{pickup_time}}</p><p><strong>Delivery:</strong> {{delivery_address}} at {{delivery_time}}</p><p>Safe travels!</p></body></html>',
    'Load {{load_number}} Accepted\nDriver: {{driver_name}}\nRoute: {{origin_city}}, {{origin_state}} to {{dest_city}}, {{dest_state}}\nRate: ${{rate_total}}\nPickup: {{pickup_address}} at {{pickup_time}}\nDelivery: {{delivery_address}} at {{delivery_time}}',
    ARRAY['driver_name','load_number','origin_city','origin_state','dest_city','dest_state','rate_total','pickup_address','pickup_time','delivery_address','delivery_time']
),
(
    'broker_confirm',
    'Load {{load_number}} Assigned — {{driver_name}}',
    '<html><body><h2>Driver Assigned</h2><p><strong>Broker:</strong> {{broker_name}}</p><p><strong>Driver:</strong> {{driver_name}}</p><p><strong>Load:</strong> {{load_number}}</p><p><strong>Pickup:</strong> {{pickup_at}}</p><p><strong>Delivery Target:</strong> {{delivery_by}}</p><p>Driver has been notified and is en route to pickup.</p></body></html>',
    'Driver Assigned\nBroker: {{broker_name}}\nDriver: {{driver_name}}\nLoad: {{load_number}}\nPickup: {{pickup_at}}\nDelivery Target: {{delivery_by}}',
    ARRAY['broker_name','driver_name','load_number','pickup_at','delivery_by']
),
(
    'payout_summary',
    'Your Weekly Earnings — {{week_ending}}',
    '<html><body><h2>Weekly Payout Summary</h2><p><strong>Week Ending:</strong> {{week_ending}}</p><p><strong>Total Loads:</strong> {{load_count}}</p><p><strong>Gross Revenue:</strong> ${{gross_revenue}}</p><p><strong>Fees & Deductions:</strong> -${{total_deductions}}</p><p><strong>Net Payout:</strong> <strong>${{net_payout}}</strong></p><p>Payout scheduled for {{payout_date}}.</p></body></html>',
    'Weekly Payout Summary\nWeek Ending: {{week_ending}}\nTotal Loads: {{load_count}}\nGross Revenue: ${{gross_revenue}}\nFees & Deductions: -${{total_deductions}}\nNet Payout: ${{net_payout}}\nPayout scheduled for {{payout_date}}.',
    ARRAY['week_ending','load_count','gross_revenue','total_deductions','net_payout','payout_date']
) ON CONFLICT (name) DO NOTHING;

-- email_attachments table — store attachment metadata for audit/replay
CREATE TABLE IF NOT EXISTS email_attachments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email_log_id uuid NOT NULL REFERENCES email_log(id) ON DELETE CASCADE,
    filename text NOT NULL,
    mime_type text,
    file_size int,
    storage_url text,  -- S3 or Supabase Storage path
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_email_attachments_email ON email_attachments(email_log_id);

-- Create pix_receipts table for Pix comprovantes
CREATE TABLE IF NOT EXISTS pix_receipts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  transfer_id UUID NOT NULL,
  customer_id UUID NOT NULL,
  direction TEXT NOT NULL CHECK (direction IN ('sent', 'received')),
  amount NUMERIC(15,2) NOT NULL,
  description TEXT,
  end_to_end_id TEXT NOT NULL,
  funded_by TEXT NOT NULL DEFAULT 'balance',
  installments INTEGER DEFAULT 1,
  sender_name TEXT,
  sender_document TEXT,
  sender_bank TEXT,
  sender_branch TEXT,
  sender_account TEXT,
  recipient_name TEXT,
  recipient_document TEXT,
  recipient_bank TEXT,
  recipient_branch TEXT,
  recipient_account TEXT,
  recipient_key_type TEXT,
  recipient_key_value TEXT,
  transaction_id TEXT,
  status TEXT NOT NULL DEFAULT 'completed',
  executed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_pix_receipts_customer ON pix_receipts(customer_id);
CREATE INDEX IF NOT EXISTS idx_pix_receipts_transfer ON pix_receipts(transfer_id);
CREATE INDEX IF NOT EXISTS idx_pix_receipts_e2e ON pix_receipts(end_to_end_id);

-- Add counterparty column to customer_transactions table.
-- This stores the name of the other party in the transaction (e.g., recipient/sender).
ALTER TABLE customer_transactions ADD COLUMN IF NOT EXISTS counterparty TEXT DEFAULT '';

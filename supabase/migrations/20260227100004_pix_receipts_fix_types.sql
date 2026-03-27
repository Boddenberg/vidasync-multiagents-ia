-- Fix pix_receipts: change UUID columns to TEXT for compatibility with legacy customer IDs
ALTER TABLE pix_receipts ALTER COLUMN customer_id TYPE TEXT;
ALTER TABLE pix_receipts ALTER COLUMN transfer_id TYPE TEXT;

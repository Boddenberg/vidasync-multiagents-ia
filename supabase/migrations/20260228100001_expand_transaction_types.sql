-- Migration: Expand customer_transactions type CHECK constraint
-- The original migration 001 only allowed ('credit', 'debit').
-- The service layer needs pix_sent, pix_received, debit_purchase, credit_purchase,
-- transfer_in, transfer_out, bill_payment types.
-- Run this in Supabase SQL Editor (Dashboard > SQL Editor)

ALTER TABLE customer_transactions
    DROP CONSTRAINT IF EXISTS customer_transactions_type_check;
ALTER TABLE customer_transactions
    ADD CONSTRAINT customer_transactions_type_check
    CHECK (type IN (
        'credit', 'debit',
        'pix_sent', 'pix_received',
        'debit_purchase', 'credit_purchase',
        'transfer_in', 'transfer_out',
        'bill_payment'
    ));

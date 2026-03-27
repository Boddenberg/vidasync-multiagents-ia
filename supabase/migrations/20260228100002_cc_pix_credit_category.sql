-- Migration: Add 'pix_credit' to credit_card_transactions category CHECK constraint
-- The service uses category='pix_credit' for PIX via credit card transactions.

ALTER TABLE credit_card_transactions
    DROP CONSTRAINT IF EXISTS credit_card_transactions_category_check;
ALTER TABLE credit_card_transactions
    ADD CONSTRAINT credit_card_transactions_category_check
    CHECK (category IN (
        'food', 'transport', 'fuel', 'office_supplies', 'technology',
        'travel', 'subscription', 'marketing', 'utilities', 'insurance',
        'maintenance', 'professional_services', 'tax', 'pix_credit', 'other'
    ));

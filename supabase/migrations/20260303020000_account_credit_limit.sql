-- ============================================================
-- Add credit_limit and available_credit_limit to accounts table.
-- This stores the pre-approved credit limit at the account level.
-- When a customer requests a credit card, the card limit is
-- deducted from available_credit_limit.
-- ============================================================

ALTER TABLE accounts
    ADD COLUMN IF NOT EXISTS credit_limit NUMERIC(15,2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS available_credit_limit NUMERIC(15,2) DEFAULT 0.00;
COMMENT ON COLUMN accounts.credit_limit IS 'Limite de crédito pré-aprovado para o cliente';
COMMENT ON COLUMN accounts.available_credit_limit IS 'Limite de crédito disponível (credit_limit - soma dos limites dos cartões)';

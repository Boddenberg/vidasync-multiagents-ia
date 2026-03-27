-- Migration: Add financial context columns to llm_transcripts
-- Stores which context providers were used and the full serialized context

ALTER TABLE llm_transcripts
    ADD COLUMN IF NOT EXISTS financial_context_keys text[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS financial_context_raw  jsonb  DEFAULT NULL;
COMMENT ON COLUMN llm_transcripts.financial_context_keys IS 'Sub-contextos financeiros enviados ao agente neste turno (account, cards, pix, billing, profile)';
COMMENT ON COLUMN llm_transcripts.financial_context_raw  IS 'JSON completo do FinancialContext enviado ao agente neste turno';
-- Index for querying transcripts that include financial context
CREATE INDEX IF NOT EXISTS idx_llm_transcripts_has_financial_ctx
    ON llm_transcripts USING gin (financial_context_keys)
    WHERE financial_context_keys != '{}';

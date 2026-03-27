-- ============================================================
-- Tabela: llm_evaluations
-- Resultado da avaliação LLM-as-Judge de uma conversa completa.
-- Uma linha por avaliação (1 customer_id pode ter N avaliações).
-- ============================================================

CREATE TABLE IF NOT EXISTS llm_evaluations (
    id                      UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id             TEXT NOT NULL,
    overall_score           DOUBLE PRECISION NOT NULL,
    verdict                 TEXT NOT NULL,              -- "pass" | "fail" | "warning"
    summary                 TEXT,
    num_turns               INT,
    -- metadata do juiz
    judge_model             TEXT,                       -- ex: gpt-4o-mini
    judge_prompt_version    TEXT,                       -- ex: 1.0.0
    tokens_used             INT,
    estimated_cost_usd      DOUBLE PRECISION,
    evaluation_duration_ms  DOUBLE PRECISION,
    created_at              TIMESTAMPTZ DEFAULT now()
);
-- ============================================================
-- Tabela: llm_evaluation_criteria
-- Cada critério avaliado (correctness, safety, coherence, etc.)
-- ============================================================

CREATE TABLE IF NOT EXISTS llm_evaluation_criteria (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    evaluation_id   UUID NOT NULL REFERENCES llm_evaluations(id) ON DELETE CASCADE,
    criterion       TEXT NOT NULL,              -- "correctness", "safety", etc.
    score           DOUBLE PRECISION NOT NULL,
    max_score       DOUBLE PRECISION NOT NULL,
    reasoning       TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);
-- ============================================================
-- Tabela: llm_evaluation_improvements
-- Sugestões de melhoria retornadas pelo juiz.
-- ============================================================

CREATE TABLE IF NOT EXISTS llm_evaluation_improvements (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    evaluation_id   UUID NOT NULL REFERENCES llm_evaluations(id) ON DELETE CASCADE,
    suggestion      TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);
-- Índices
CREATE INDEX IF NOT EXISTS idx_llm_evaluations_customer       ON llm_evaluations(customer_id);
CREATE INDEX IF NOT EXISTS idx_llm_evaluations_verdict         ON llm_evaluations(verdict);
CREATE INDEX IF NOT EXISTS idx_llm_evaluations_created         ON llm_evaluations(created_at);
CREATE INDEX IF NOT EXISTS idx_llm_eval_criteria_eval_id       ON llm_evaluation_criteria(evaluation_id);
CREATE INDEX IF NOT EXISTS idx_llm_eval_improvements_eval_id   ON llm_evaluation_improvements(evaluation_id);
-- RLS
ALTER TABLE llm_evaluations             ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_evaluation_criteria     ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_evaluation_improvements ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full_access_evaluations"
    ON llm_evaluations FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "service_role_full_access_eval_criteria"
    ON llm_evaluation_criteria FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "service_role_full_access_eval_improvements"
    ON llm_evaluation_improvements FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

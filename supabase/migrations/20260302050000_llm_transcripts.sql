-- ============================================================
-- Tabela: llm_transcripts
-- Guarda cada turno de conversa entre usuário e LLM para avaliação
-- posterior via LLM-as-Judge. Inserção assíncrona — não bloqueia o chat.
-- ============================================================

CREATE TABLE IF NOT EXISTS llm_transcripts (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_id     TEXT NOT NULL,
    query           TEXT NOT NULL,             -- pergunta do usuário
    answer          TEXT NOT NULL,             -- resposta da LLM
    step            TEXT,                      -- step do onboarding (se houver)
    intent          TEXT,                      -- intent detectada pelo agente
    confidence      DOUBLE PRECISION,          -- confiança do agente na classificação
    model           TEXT,                      -- modelo utilizado (ex: gpt-4o-mini)
    latency_ms      BIGINT,                   -- tempo de resposta do agente em ms
    created_at      TIMESTAMPTZ DEFAULT now()
);
-- Índices para consultas de avaliação
CREATE INDEX IF NOT EXISTS idx_llm_transcripts_customer_id ON llm_transcripts(customer_id);
CREATE INDEX IF NOT EXISTS idx_llm_transcripts_created_at  ON llm_transcripts(created_at);
-- RLS: acesso via service_role
ALTER TABLE llm_transcripts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "service_role_full_access_llm_transcripts" ON llm_transcripts
    FOR ALL USING (true) WITH CHECK (true);

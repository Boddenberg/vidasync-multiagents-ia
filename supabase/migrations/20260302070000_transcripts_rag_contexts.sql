-- ============================================================
-- Adiciona coluna rag_contexts à tabela llm_transcripts
-- Armazena os chunks de contexto RAG usados pelo agente em cada turno.
-- Necessário para enviar o trio (query, answer, contexts) ao LLM-as-Judge.
-- ============================================================

ALTER TABLE llm_transcripts
    ADD COLUMN IF NOT EXISTS rag_contexts JSONB DEFAULT '[]'::jsonb;
COMMENT ON COLUMN llm_transcripts.rag_contexts IS 'Chunks de contexto RAG usados pelo agente neste turno';

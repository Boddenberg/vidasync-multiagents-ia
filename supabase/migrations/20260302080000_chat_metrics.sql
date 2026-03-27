-- ============================================================
-- Migration: chat_metrics
-- 1. Adiciona colunas error_occurred e tokens_used na llm_transcripts
-- 2. Cria função RPC get_chat_metrics() que retorna todas as métricas
--    pré-computadas para o frontend ("mastigadas").
-- ============================================================

-- 1. Novas colunas em llm_transcripts
ALTER TABLE llm_transcripts
    ADD COLUMN IF NOT EXISTS error_occurred BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS tokens_used    INT     DEFAULT 0;
COMMENT ON COLUMN llm_transcripts.error_occurred IS 'Se houve erro na chamada ao agente neste turno';
COMMENT ON COLUMN llm_transcripts.tokens_used    IS 'Total de tokens consumidos neste turno (prompt + completion)';
-- 2. Função RPC que computa todas as métricas do chat
CREATE OR REPLACE FUNCTION get_chat_metrics()
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSON;
BEGIN
    WITH transcript_stats AS (
        SELECT
            COUNT(*)                                              AS total_requests,
            COALESCE(AVG(latency_ms), 0)                          AS avg_latency_ms,
            COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms), 0) AS p95_latency_ms,
            COALESCE(AVG(tokens_used), 0)                         AS avg_tokens_per_request,
            COALESCE(SUM(tokens_used), 0)                         AS total_tokens,
            COUNT(*) FILTER (WHERE error_occurred = true)         AS error_count,
            COUNT(*) FILTER (WHERE error_occurred = false)        AS success_count
        FROM llm_transcripts
    ),
    rag_stats AS (
        -- Média de faithfulness e context_relevance da ÚLTIMA avaliação de cada cliente
        SELECT
            COALESCE(AVG(
                CASE WHEN c.criterion = 'faithfulness' THEN c.score / NULLIF(c.max_score, 0) END
            ), 0) AS avg_faithfulness,
            COALESCE(AVG(
                CASE WHEN c.criterion = 'context_relevance' THEN c.score / NULLIF(c.max_score, 0) END
            ), 0) AS avg_context_relevance
        FROM llm_evaluation_criteria c
        JOIN llm_evaluations e ON e.id = c.evaluation_id
        WHERE c.criterion IN ('faithfulness', 'context_relevance')
    ),
    cost_stats AS (
        -- Custo estimado: GPT-4o-mini ~$0.15/1M input + $0.60/1M output
        -- Simplificação: $0.0004 por 1K tokens combinados
        SELECT
            COALESCE(SUM(tokens_used), 0) * 0.0000004 AS total_estimated_cost
        FROM llm_transcripts
    )
    SELECT json_build_object(
        'total_requests',          ts.total_requests,
        'avg_latency_ms',          ROUND(ts.avg_latency_ms::numeric, 1),
        'p95_latency_ms',          ROUND(ts.p95_latency_ms::numeric, 1),
        'avg_tokens_per_request',  ROUND(ts.avg_tokens_per_request::numeric, 1),
        'total_tokens',            ts.total_tokens,
        'error_count',             ts.error_count,
        'success_count',           ts.success_count,
        'error_rate_pct',          CASE WHEN ts.total_requests > 0
                                       THEN ROUND((ts.error_count::numeric / ts.total_requests * 100), 2)
                                       ELSE 0 END,
        'estimated_cost_usd',      ROUND(cs.total_estimated_cost::numeric, 6),
        'rag_score_pct',           CASE WHEN (rs.avg_faithfulness + rs.avg_context_relevance) > 0
                                       THEN ROUND(((rs.avg_faithfulness + rs.avg_context_relevance) / 2 * 100)::numeric, 1)
                                       ELSE 0 END,
        'avg_faithfulness',        ROUND(rs.avg_faithfulness::numeric, 3),
        'avg_context_relevance',   ROUND(rs.avg_context_relevance::numeric, 3),
        'cache_hit_rate_pct',      0
    ) INTO result
    FROM transcript_stats ts
    CROSS JOIN rag_stats rs
    CROSS JOIN cost_stats cs;

    RETURN result;
END;
$$;

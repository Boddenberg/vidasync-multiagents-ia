-- ============================================================
-- Migration: transcript_evaluated + bfa_latency_ms
-- 1. Adiciona coluna 'evaluated' para evitar reenvio de
--    transcrições já avaliadas pelo LLM-as-Judge.
-- 2. Adiciona coluna 'bfa_latency_ms' para medir latência
--    total do BFA (request HTTP inteiro, incluindo validação).
-- ============================================================

-- Flag para saber se a transcrição já foi avaliada
ALTER TABLE llm_transcripts
    ADD COLUMN IF NOT EXISTS evaluated BOOLEAN DEFAULT false;
-- Latência total do BFA (do request ao response do handler)
ALTER TABLE llm_transcripts
    ADD COLUMN IF NOT EXISTS bfa_latency_ms BIGINT;
-- Índice para queries que filtram não-avaliados
CREATE INDEX IF NOT EXISTS idx_llm_transcripts_evaluated
    ON llm_transcripts(customer_id, evaluated)
    WHERE evaluated = false;
-- Atualizar get_chat_metrics() para incluir avg BFA latency
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
            COUNT(*) FILTER (WHERE error_occurred = false)        AS success_count,
            COALESCE(AVG(bfa_latency_ms) FILTER (WHERE bfa_latency_ms > 0), 0) AS avg_bfa_latency_ms,
            COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY bfa_latency_ms) FILTER (WHERE bfa_latency_ms > 0), 0) AS p95_bfa_latency_ms
        FROM llm_transcripts
    ),
    rag_stats AS (
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
        SELECT
            COALESCE(SUM(tokens_used), 0) * 0.0000004 AS total_estimated_cost
        FROM llm_transcripts
    ),
    eval_stats AS (
        SELECT
            COUNT(*)                                                    AS total_evaluations,
            COALESCE(AVG(overall_score), 0)                             AS avg_overall_score,
            COUNT(*) FILTER (WHERE verdict = 'pass')                    AS pass_count,
            COUNT(*) FILTER (WHERE verdict = 'fail')                    AS fail_count,
            COUNT(*) FILTER (WHERE verdict = 'warning')                 AS warning_count,
            COALESCE(AVG(num_turns), 0)                                 AS avg_turns_per_conversation,
            COALESCE(AVG(evaluation_duration_ms), 0)                    AS avg_eval_duration_ms,
            COALESCE(SUM(estimated_cost_usd), 0)                        AS total_eval_cost_usd
        FROM llm_evaluations
    ),
    criteria_breakdown AS (
        SELECT
            COALESCE(json_agg(
                json_build_object(
                    'criterion', cb.criterion,
                    'avg_score', cb.avg_score,
                    'max_score', cb.max_score,
                    'avg_pct',   cb.avg_pct
                )
            ), '[]'::json) AS criteria
        FROM (
            SELECT
                c.criterion,
                ROUND(AVG(c.score)::numeric, 2)                                   AS avg_score,
                ROUND(MAX(c.max_score)::numeric, 2)                               AS max_score,
                ROUND((AVG(c.score / NULLIF(c.max_score, 0)) * 100)::numeric, 1)  AS avg_pct
            FROM llm_evaluation_criteria c
            GROUP BY c.criterion
            ORDER BY c.criterion
        ) cb
    ),
    top_improvements AS (
        SELECT
            COALESCE(json_agg(
                json_build_object(
                    'suggestion', ti.suggestion,
                    'count',      ti.cnt
                )
            ), '[]'::json) AS improvements
        FROM (
            SELECT
                suggestion,
                COUNT(*) AS cnt
            FROM llm_evaluation_improvements
            GROUP BY suggestion
            ORDER BY cnt DESC
            LIMIT 5
        ) ti
    )
    SELECT json_build_object(
        'agent_performance', json_build_object(
            'avg_latency_ms',          ROUND(ts.avg_latency_ms::numeric, 1),
            'p95_latency_ms',          ROUND(ts.p95_latency_ms::numeric, 1),
            'avg_bfa_latency_ms',      ROUND(ts.avg_bfa_latency_ms::numeric, 1),
            'p95_bfa_latency_ms',      ROUND(ts.p95_bfa_latency_ms::numeric, 1),
            'avg_tokens_per_request',  ROUND(ts.avg_tokens_per_request::numeric, 1),
            'total_tokens',            ts.total_tokens,
            'estimated_cost_usd',      ROUND(cs.total_estimated_cost::numeric, 6),
            'total_requests',          ts.total_requests,
            'error_rate_pct',          CASE WHEN ts.total_requests > 0
                                           THEN ROUND((ts.error_count::numeric / ts.total_requests * 100), 2)
                                           ELSE 0 END,
            'error_count',             ts.error_count,
            'success_count',           ts.success_count,
            'cache_hit_rate_pct',      0
        ),
        'rag_quality', json_build_object(
            'score_pct',             CASE WHEN (rs.avg_faithfulness + rs.avg_context_relevance) > 0
                                         THEN ROUND(((rs.avg_faithfulness + rs.avg_context_relevance) / 2 * 100)::numeric, 1)
                                         ELSE 0 END,
            'avg_faithfulness',      ROUND(rs.avg_faithfulness::numeric, 3),
            'avg_context_relevance', ROUND(rs.avg_context_relevance::numeric, 3)
        ),
        'llm_judge', json_build_object(
            'total_evaluations',          es.total_evaluations,
            'avg_overall_score',          ROUND(es.avg_overall_score::numeric, 2),
            'pass_rate_pct',              CASE WHEN es.total_evaluations > 0
                                               THEN ROUND((es.pass_count::numeric / es.total_evaluations * 100), 1)
                                               ELSE 0 END,
            'pass_count',                 es.pass_count,
            'fail_count',                 es.fail_count,
            'warning_count',              es.warning_count,
            'avg_turns_per_conversation', ROUND(es.avg_turns_per_conversation::numeric, 1),
            'avg_eval_duration_ms',       ROUND(es.avg_eval_duration_ms::numeric, 1),
            'total_eval_cost_usd',        ROUND(es.total_eval_cost_usd::numeric, 6),
            'criteria_breakdown',         crit.criteria,
            'top_improvements',           ti.improvements
        )
    ) INTO result
    FROM transcript_stats ts
    CROSS JOIN rag_stats rs
    CROSS JOIN cost_stats cs
    CROSS JOIN eval_stats es
    CROSS JOIN criteria_breakdown crit
    CROSS JOIN top_improvements ti;

    RETURN result;
END;
$$;

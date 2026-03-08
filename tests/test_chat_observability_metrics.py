from vidasync_multiagents_ia.observability import (
    record_ai_router_request,
    record_ai_router_timeout,
    record_chat_fallback,
    record_chat_flow_execution,
    record_chat_rag_usage,
    record_chat_stage_duration,
    record_chat_timeout,
    record_chat_tool_execution,
    record_chat_tool_failure,
    render_metrics_prometheus,
)


def test_metrics_expoe_contadores_de_chat_e_ai_router() -> None:
    record_chat_flow_execution(
        flow="chat_conversacional",
        engine="langgraph",
        intencao="pedir_receitas",
        pipeline="rag_conhecimento_nutricional",
        handler="handler_fluxo_receitas_personalizadas",
        status="sucesso",
        duration_ms=123.45,
    )
    record_chat_stage_duration(engine="langgraph", stage="detectar_intencao", status="ok", duration_ms=12.3)
    record_chat_tool_execution(tool="consultar_conhecimento_nutricional", status="sucesso", duration_ms=88.8)
    record_chat_tool_failure(tool="calcular_imc", error_type="ServiceError")
    record_chat_fallback(flow="chat_conversacional", reason="router_exception")
    record_chat_timeout(flow="chat_conversacional", stage="tool.calcular_imc")
    record_chat_rag_usage(context="chat_receitas_flow", used=True, documents_count=3)
    record_ai_router_request(contexto="chat", status="sucesso", duration_ms=56.7)
    record_ai_router_timeout(contexto="chat")

    metrics = render_metrics_prometheus()
    assert "vidasync_chat_flow_requests_total" in metrics
    assert 'flow="chat_conversacional"' in metrics
    assert "vidasync_chat_stage_duration_ms_sum" in metrics
    assert 'stage="detectar_intencao"' in metrics
    assert "vidasync_chat_tool_requests_total" in metrics
    assert 'tool="consultar_conhecimento_nutricional"' in metrics
    assert "vidasync_chat_tool_failures_total" in metrics
    assert 'tool="calcular_imc"' in metrics
    assert "vidasync_chat_fallbacks_total" in metrics
    assert "vidasync_chat_timeouts_total" in metrics
    assert "vidasync_chat_rag_requests_total" in metrics
    assert "vidasync_ai_router_requests_total" in metrics
    assert "vidasync_ai_router_timeouts_total" in metrics

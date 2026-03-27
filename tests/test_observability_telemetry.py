from contextlib import ExitStack

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.observability.context import (
    reset_request_id,
    reset_trace_id,
    set_request_id,
    set_trace_id,
)
from vidasync_multiagents_ia.observability.telemetry import TelemetryCollector


def test_telemetry_collector_agrega_totais_de_execucao() -> None:
    with ExitStack() as stack:
        request_token = set_request_id("req-123")
        trace_token = set_trace_id("trace-123")
        stack.callback(reset_trace_id, trace_token)
        stack.callback(reset_request_id, request_token)

        collector = TelemetryCollector(settings=Settings())
        collector.set_request_context(
            method="POST",
            path="/v1/openai/chat",
            query={"debug": "1"},
            client_ip="127.0.0.1",
            contexto="chat",
        )
        collector.update_run(
            agent="openai_chat",
            conversation_id="conv-123",
            status="parcial",
            warnings_count=2,
            precisa_revisao=True,
        )
        collector.add_llm_call(
            provider="openai",
            operation="generate_text",
            model="gpt-4o-mini",
            status="ok",
            duration_ms=123.4,
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
            cost_usd=0.000027,
        )
        collector.add_tool_call(
            tool_name="consultar_conhecimento_nutricional",
            status="sucesso",
            duration_ms=88.8,
            warnings_count=1,
            precisa_revisao=True,
        )
        collector.add_stage_event(
            event_type="chat_fallback",
            name="chat_conversacional",
            status="fallback",
            reason="router_exception",
        )
        collector.add_stage_event(
            event_type="chat_rag",
            name="chat_receitas_flow",
            status="used",
            used=True,
            documents_count=3,
        )
        collector.finalize_request(status_code=200, duration_ms=456.7, timeout=False)

        batch = collector.build_batch()

    assert batch.agent_run is not None
    assert batch.agent_run["request_id"] == "req-123"
    assert batch.agent_run["trace_id"] == "trace-123"
    assert batch.agent_run["agent"] == "openai_chat"
    assert batch.agent_run["conversation_id"] == "conv-123"
    assert batch.agent_run["llm_calls_count"] == 1
    assert batch.agent_run["tool_calls_count"] == 1
    assert batch.agent_run["stage_events_count"] == 2
    assert batch.agent_run["fallback_count"] == 1
    assert batch.agent_run["rag_used"] is True
    assert batch.agent_run["rag_docs_count"] == 3
    assert batch.agent_run["total_input_tokens"] == 100
    assert batch.agent_run["total_output_tokens"] == 20
    assert batch.agent_run["total_tokens"] == 120
    assert batch.agent_run["total_cost_usd"] == 0.000027
    assert batch.agent_run["warnings_count"] == 2
    assert batch.agent_run["precisa_revisao"] is True
    assert batch.agent_run["http_status_code"] == 200
    assert len(batch.llm_calls) == 1
    assert len(batch.tool_calls) == 1
    assert len(batch.stage_events) == 2

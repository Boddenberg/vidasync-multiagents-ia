from vidasync_multiagents_ia.observability.context import (
    get_trace_id,
    reset_request_id,
    reset_trace_id,
    set_request_id,
    set_trace_id,
)


def test_trace_id_usa_fallback_do_request_id() -> None:
    request_token = set_request_id("req-123")
    trace_token = set_trace_id("-")
    try:
        assert get_trace_id() == "req-123"
    finally:
        reset_trace_id(trace_token)
        reset_request_id(request_token)


def test_trace_id_prioriza_valor_explicito() -> None:
    request_token = set_request_id("req-123")
    trace_token = set_trace_id("trace-abc")
    try:
        assert get_trace_id() == "trace-abc"
    finally:
        reset_trace_id(trace_token)
        reset_request_id(request_token)

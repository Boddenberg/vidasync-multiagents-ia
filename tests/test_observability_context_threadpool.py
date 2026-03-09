from concurrent.futures import ThreadPoolExecutor

from vidasync_multiagents_ia.observability.context import (
    get_request_id,
    get_trace_id,
    reset_request_id,
    reset_trace_id,
    set_request_id,
    set_trace_id,
    submit_with_context,
)


def test_submit_with_context_propagates_request_and_trace_ids() -> None:
    request_token = set_request_id("req-thread-123")
    trace_token = set_trace_id("trace-thread-456")
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = submit_with_context(
                executor,
                lambda: (get_request_id(), get_trace_id()),
            )
            request_id, trace_id = future.result(timeout=2)
        assert request_id == "req-thread-123"
        assert trace_id == "trace-thread-456"
    finally:
        reset_trace_id(trace_token)
        reset_request_id(request_token)

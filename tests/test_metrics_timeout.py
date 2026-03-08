from vidasync_multiagents_ia.observability import (
    record_external_timeout,
    record_http_timeout,
    render_metrics_prometheus,
)


def test_metrics_expoe_contadores_de_timeout() -> None:
    record_http_timeout(method="POST", path="/ai/router")
    record_external_timeout(client="openai", operation="generate_json_from_text")

    metrics = render_metrics_prometheus()
    assert "vidasync_http_timeouts_total" in metrics
    assert 'vidasync_http_timeouts_total{method="POST",path="/ai/router"}' in metrics
    assert "vidasync_external_timeouts_total" in metrics
    assert 'vidasync_external_timeouts_total{client="openai",operation="generate_json_from_text"}' in metrics

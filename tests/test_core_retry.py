from vidasync_multiagents_ia.core.retry import RetryConfig, compute_backoff, is_retryable_http_status


def test_compute_backoff_grows_exponentially() -> None:
    config = RetryConfig(max_attempts=5, base_delay_seconds=1.0, max_delay_seconds=100.0, jitter_factor=0.0)
    assert compute_backoff(1, config, rand=0.5) == 1.0
    assert compute_backoff(2, config, rand=0.5) == 2.0
    assert compute_backoff(3, config, rand=0.5) == 4.0


def test_compute_backoff_caps_at_max() -> None:
    config = RetryConfig(max_attempts=10, base_delay_seconds=1.0, max_delay_seconds=3.0, jitter_factor=0.0)
    assert compute_backoff(10, config, rand=0.5) == 3.0


def test_compute_backoff_applies_jitter() -> None:
    config = RetryConfig(max_attempts=3, base_delay_seconds=1.0, max_delay_seconds=10.0, jitter_factor=0.5)
    assert compute_backoff(1, config, rand=0.0) == 0.5
    assert compute_backoff(1, config, rand=1.0) == 1.5


def test_is_retryable_http_status() -> None:
    assert is_retryable_http_status(500)
    assert is_retryable_http_status(503)
    assert is_retryable_http_status(429)
    assert not is_retryable_http_status(400)
    assert not is_retryable_http_status(404)
    assert not is_retryable_http_status(200)

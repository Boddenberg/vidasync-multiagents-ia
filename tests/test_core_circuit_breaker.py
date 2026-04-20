import time

import pytest

from vidasync_multiagents_ia.core.circuit_breaker import CircuitBreaker, CircuitOpenError


def test_circuit_breaker_starts_closed() -> None:
    breaker = CircuitBreaker(name="x", failure_threshold=3, recovery_seconds=1.0)
    assert breaker.state == "closed"
    breaker.before_call()


def test_circuit_breaker_opens_after_threshold() -> None:
    breaker = CircuitBreaker(name="x", failure_threshold=2, recovery_seconds=5.0)
    breaker.record_failure()
    assert breaker.state == "closed"
    breaker.record_failure()
    assert breaker.state == "open"
    with pytest.raises(CircuitOpenError):
        breaker.before_call()


def test_circuit_breaker_half_open_after_recovery() -> None:
    breaker = CircuitBreaker(name="x", failure_threshold=1, recovery_seconds=0.01)
    breaker.record_failure()
    assert breaker.state == "open"
    time.sleep(0.02)
    assert breaker.state == "half_open"
    breaker.before_call()


def test_circuit_breaker_success_resets() -> None:
    breaker = CircuitBreaker(name="x", failure_threshold=2, recovery_seconds=5.0)
    breaker.record_failure()
    breaker.record_success()
    assert breaker.state == "closed"
    breaker.record_failure()
    assert breaker.state == "closed"

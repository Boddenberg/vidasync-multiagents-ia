import pytest

from vidasync_multiagents_ia.core.rate_limit import (
    InMemoryTokenBucketRateLimiter,
    TokenBucketConfig,
)


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_bucket_allows_up_to_capacity_then_blocks() -> None:
    clock = _FakeClock()
    limiter = InMemoryTokenBucketRateLimiter(
        TokenBucketConfig(capacity=3, refill_per_second=1),
        clock=clock,
    )

    assert limiter.check("ip-1").allowed is True
    assert limiter.check("ip-1").allowed is True
    assert limiter.check("ip-1").allowed is True
    blocked = limiter.check("ip-1")
    assert blocked.allowed is False
    assert blocked.retry_after_seconds == pytest.approx(1.0, rel=1e-3)


def test_bucket_refills_over_time() -> None:
    clock = _FakeClock()
    limiter = InMemoryTokenBucketRateLimiter(
        TokenBucketConfig(capacity=2, refill_per_second=1),
        clock=clock,
    )

    limiter.check("k")
    limiter.check("k")
    assert limiter.check("k").allowed is False

    clock.advance(1.0)
    assert limiter.check("k").allowed is True


def test_buckets_are_isolated_per_key() -> None:
    clock = _FakeClock()
    limiter = InMemoryTokenBucketRateLimiter(
        TokenBucketConfig(capacity=1, refill_per_second=1),
        clock=clock,
    )
    assert limiter.check("a").allowed is True
    assert limiter.check("b").allowed is True
    assert limiter.check("a").allowed is False
    assert limiter.check("b").allowed is False


def test_config_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError):
        TokenBucketConfig(capacity=0, refill_per_second=1)
    with pytest.raises(ValueError):
        TokenBucketConfig(capacity=1, refill_per_second=0)

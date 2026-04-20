"""In-memory token-bucket rate limiter.

The `RateLimiter` Protocol decouples the middleware from the concrete
store so a Redis/Supabase-backed implementation can be swapped in later
without touching call sites.
"""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Protocol


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: float
    retry_after_seconds: float


class RateLimiter(Protocol):
    def check(self, key: str) -> RateLimitDecision:
        ...


@dataclass(frozen=True)
class TokenBucketConfig:
    capacity: float
    refill_per_second: float

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be > 0")
        if self.refill_per_second <= 0:
            raise ValueError("refill_per_second must be > 0")


class InMemoryTokenBucketRateLimiter:
    def __init__(self, config: TokenBucketConfig, *, clock: callable = monotonic) -> None:
        self._config = config
        self._clock = clock
        self._lock = Lock()
        self._buckets: dict[str, tuple[float, float]] = {}

    def check(self, key: str) -> RateLimitDecision:
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self._config.capacity, now))
            elapsed = max(0.0, now - last)
            tokens = min(self._config.capacity, tokens + elapsed * self._config.refill_per_second)
            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[key] = (tokens, now)
                return RateLimitDecision(allowed=True, remaining=tokens, retry_after_seconds=0.0)
            deficit = 1.0 - tokens
            retry_after = deficit / self._config.refill_per_second
            self._buckets[key] = (tokens, now)
            return RateLimitDecision(allowed=False, remaining=tokens, retry_after_seconds=retry_after)

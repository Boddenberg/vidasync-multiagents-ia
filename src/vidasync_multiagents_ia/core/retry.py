"""Exponential backoff + jitter helpers for transient HTTP retries."""
from __future__ import annotations

from dataclasses import dataclass
from random import uniform


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 1
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 4.0
    jitter_factor: float = 0.25


def compute_backoff(attempt: int, config: RetryConfig, *, rand: float | None = None) -> float:
    exponent = max(0, int(attempt) - 1)
    base = min(config.base_delay_seconds * (2**exponent), config.max_delay_seconds)
    jitter = base * max(0.0, config.jitter_factor)
    offset = uniform(-jitter, jitter) if rand is None else (rand * 2.0 - 1.0) * jitter
    return max(0.0, base + offset)


def is_retryable_http_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600

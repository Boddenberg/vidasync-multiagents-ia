"""Minimal thread-safe circuit breaker.

Three states: ``closed`` (calls pass), ``open`` (calls short-circuit and
raise ``CircuitOpenError``), ``half_open`` (one probe allowed). Intended
for wrapping outbound HTTP calls so that repeated failures degrade
quickly instead of piling timeouts on the caller.
"""
from __future__ import annotations

from threading import Lock
from time import monotonic


class CircuitOpenError(RuntimeError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Circuit '{name}' is open.")
        self.name = name


class CircuitBreaker:
    def __init__(
        self,
        *,
        name: str,
        failure_threshold: int = 5,
        recovery_seconds: float = 30.0,
    ) -> None:
        self._name = name
        self._failure_threshold = max(1, int(failure_threshold))
        self._recovery_seconds = max(0.0, float(recovery_seconds))
        self._lock = Lock()
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> str:
        with self._lock:
            return self._state_unlocked()

    def _state_unlocked(self) -> str:
        if self._opened_at is None:
            return "closed"
        if monotonic() - self._opened_at >= self._recovery_seconds:
            return "half_open"
        return "open"

    def before_call(self) -> None:
        with self._lock:
            state = self._state_unlocked()
            if state == "open":
                raise CircuitOpenError(self._name)

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._failure_threshold:
                self._opened_at = monotonic()

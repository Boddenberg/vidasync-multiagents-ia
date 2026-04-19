"""Thread-safe LRU cache with per-entry TTL.

Intended for memoizing idempotent outbound HTTP calls (TBCA / TACO /
Open Food Facts) where read-your-writes consistency is not required.
Entries that expire are lazily evicted on access; LRU eviction kicks
in when ``max_entries`` is reached.
"""
from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from time import monotonic
from typing import Generic, TypeVar

KeyT = TypeVar("KeyT")
ValueT = TypeVar("ValueT")


class TTLCache(Generic[KeyT, ValueT]):
    def __init__(self, *, ttl_seconds: float, max_entries: int) -> None:
        self._ttl_seconds = max(0.0, float(ttl_seconds))
        self._max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[KeyT, tuple[float, ValueT]] = OrderedDict()
        self._lock = Lock()

    @property
    def enabled(self) -> bool:
        return self._ttl_seconds > 0.0

    def get(self, key: KeyT) -> ValueT | None:
        if not self.enabled:
            return None
        now = monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= now:
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return value

    def set(self, key: KeyT, value: ValueT) -> None:
        if not self.enabled:
            return
        expires_at = monotonic() + self._ttl_seconds
        with self._lock:
            self._entries[key] = (expires_at, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

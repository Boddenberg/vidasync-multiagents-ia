"""Pluggable persistence for pipeline executions (introspection + audit)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Protocol


@dataclass(slots=True)
class ExecutionRecord:
    execution_id: str
    pipeline: str
    started_at: datetime
    trace_id: str | None = None
    conversation_id: str | None = None
    finished_at: datetime | None = None
    status: str = "running"
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionStore(Protocol):
    def create(self, record: ExecutionRecord) -> None:
        ...

    def update(
        self,
        execution_id: str,
        *,
        status: str | None = None,
        finished_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionRecord | None:
        ...

    def get(self, execution_id: str) -> ExecutionRecord | None:
        ...

    def list_recent(self, limit: int = 50) -> list[ExecutionRecord]:
        ...


class InMemoryExecutionStore:
    def __init__(self, *, max_entries: int = 1024) -> None:
        self._max_entries = max(1, int(max_entries))
        self._records: dict[str, ExecutionRecord] = {}
        self._order: list[str] = []
        self._lock = Lock()

    def create(self, record: ExecutionRecord) -> None:
        with self._lock:
            if record.execution_id in self._records:
                self._order.remove(record.execution_id)
            self._records[record.execution_id] = record
            self._order.append(record.execution_id)
            while len(self._order) > self._max_entries:
                oldest = self._order.pop(0)
                self._records.pop(oldest, None)

    def update(
        self,
        execution_id: str,
        *,
        status: str | None = None,
        finished_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionRecord | None:
        with self._lock:
            record = self._records.get(execution_id)
            if record is None:
                return None
            if status is not None:
                record.status = status
            if finished_at is not None:
                record.finished_at = finished_at
            if metadata:
                record.metadata.update(metadata)
            return record

    def get(self, execution_id: str) -> ExecutionRecord | None:
        with self._lock:
            return self._records.get(execution_id)

    def list_recent(self, limit: int = 50) -> list[ExecutionRecord]:
        limit = max(1, int(limit))
        with self._lock:
            recent_ids = list(reversed(self._order[-limit:]))
            return [self._records[record_id] for record_id in recent_ids if record_id in self._records]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

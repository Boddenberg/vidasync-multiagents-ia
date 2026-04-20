from datetime import datetime, timedelta, timezone

from vidasync_multiagents_ia.core.execution_store import (
    ExecutionRecord,
    InMemoryExecutionStore,
    now_utc,
)


def _record(execution_id: str, started_offset_s: int = 0) -> ExecutionRecord:
    return ExecutionRecord(
        execution_id=execution_id,
        pipeline="chat",
        started_at=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=started_offset_s),
    )


def test_create_and_get_roundtrip() -> None:
    store = InMemoryExecutionStore()
    record = _record("exec-1")
    store.create(record)
    assert store.get("exec-1") is record
    assert store.get("missing") is None


def test_update_mutates_fields() -> None:
    store = InMemoryExecutionStore()
    store.create(_record("exec-1"))
    finished = now_utc()
    updated = store.update("exec-1", status="succeeded", finished_at=finished, metadata={"k": "v"})
    assert updated is not None
    assert updated.status == "succeeded"
    assert updated.finished_at == finished
    assert updated.metadata == {"k": "v"}


def test_update_missing_returns_none() -> None:
    store = InMemoryExecutionStore()
    assert store.update("missing", status="succeeded") is None


def test_list_recent_newest_first() -> None:
    store = InMemoryExecutionStore()
    for i in range(3):
        store.create(_record(f"exec-{i}", started_offset_s=i))
    recent = store.list_recent(limit=2)
    assert [record.execution_id for record in recent] == ["exec-2", "exec-1"]


def test_evicts_oldest_above_max_entries() -> None:
    store = InMemoryExecutionStore(max_entries=2)
    for i in range(3):
        store.create(_record(f"exec-{i}"))
    assert store.get("exec-0") is None
    assert store.get("exec-1") is not None
    assert store.get("exec-2") is not None

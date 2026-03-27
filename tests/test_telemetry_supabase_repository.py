import json

import pytest

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.observability.telemetry import (
    SupabaseTelemetryRepository,
    TelemetryBatch,
)


class _FakeHTTPResponse:
    def read(self) -> bytes:
        return b"[]"

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_supabase_telemetry_repository_persiste_lote(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict[str, object]] = []

    def _fake_urlopen(request, timeout):
        captured.append(
            {
                "url": request.full_url,
                "timeout": timeout,
                "headers": dict(request.header_items()),
                "payload": json.loads(request.data.decode("utf-8")),
            }
        )
        return _FakeHTTPResponse()

    monkeypatch.setattr("vidasync_multiagents_ia.observability.telemetry.urlopen", _fake_urlopen)

    repository = SupabaseTelemetryRepository(
        settings=Settings(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
            telemetry_supabase_agent_runs_table="telemetry_agent_runs",
            telemetry_supabase_llm_calls_table="telemetry_llm_calls",
            telemetry_supabase_tool_calls_table="telemetry_tool_calls",
            telemetry_supabase_stage_events_table="telemetry_stage_events",
            telemetry_supabase_timeout_seconds=9.5,
        )
    )

    batch = TelemetryBatch(
        agent_run={"run_id": "run-123", "request_id": "req-123", "trace_id": "trace-123"},
        llm_calls=[{"call_id": "call-123", "run_id": "run-123"}],
        tool_calls=[{"tool_call_id": "tool-123", "run_id": "run-123"}],
        stage_events=[{"event_id": "evt-123", "run_id": "run-123"}],
    )

    repository.persist(batch)

    assert len(captured) == 4
    assert captured[0]["url"].endswith("/rest/v1/telemetry_agent_runs?on_conflict=run_id")
    assert captured[1]["url"].endswith("/rest/v1/telemetry_llm_calls?on_conflict=call_id")
    assert captured[2]["url"].endswith("/rest/v1/telemetry_tool_calls?on_conflict=tool_call_id")
    assert captured[3]["url"].endswith("/rest/v1/telemetry_stage_events?on_conflict=event_id")
    assert captured[0]["timeout"] == 9.5
    assert captured[0]["headers"]["Authorization"] == "Bearer service-role-key"

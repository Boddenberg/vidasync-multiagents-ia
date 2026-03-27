from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from contextvars import Token
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.observability.context import (
    get_request_id,
    get_telemetry_collector,
    get_trace_id,
    set_telemetry_collector,
)
from vidasync_multiagents_ia.observability.payload_preview import preview_json, sanitize_url


@dataclass(slots=True)
class TelemetryBatch:
    agent_run: dict[str, Any] | None = None
    llm_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    stage_events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return self.agent_run is None and not self.llm_calls and not self.tool_calls and not self.stage_events


class SupabaseTelemetryRepository:
    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings
        self._logger = logging.getLogger(__name__)

    @property
    def enabled(self) -> bool:
        return bool(
            self._settings.telemetry_enabled
            and self._settings.supabase_url.strip()
            and self._settings.supabase_service_role_key.strip()
            and self._settings.telemetry_supabase_agent_runs_table.strip()
            and self._settings.telemetry_supabase_llm_calls_table.strip()
            and self._settings.telemetry_supabase_tool_calls_table.strip()
            and self._settings.telemetry_supabase_stage_events_table.strip()
        )

    def persist(self, batch: TelemetryBatch) -> None:
        if not self.enabled or batch.is_empty:
            return

        run_id = (batch.agent_run or {}).get("run_id")
        self._logger.info(
            "telemetry.supabase.persist_started",
            extra={
                "telemetry_event": "telemetry.supabase.persist_started",
                "storage": {
                    "backend": "supabase",
                    "agent_runs_table": self._settings.telemetry_supabase_agent_runs_table,
                    "llm_calls_table": self._settings.telemetry_supabase_llm_calls_table,
                    "tool_calls_table": self._settings.telemetry_supabase_tool_calls_table,
                    "stage_events_table": self._settings.telemetry_supabase_stage_events_table,
                },
                "identifiers": {
                    "run_id": run_id,
                    "request_id": (batch.agent_run or {}).get("request_id"),
                    "trace_id": (batch.agent_run or {}).get("trace_id"),
                },
                "counts": {
                    "llm_calls": len(batch.llm_calls),
                    "tool_calls": len(batch.tool_calls),
                    "stage_events": len(batch.stage_events),
                },
            },
        )

        self._upsert_rows(
            table=self._settings.telemetry_supabase_agent_runs_table,
            rows=[batch.agent_run] if batch.agent_run else [],
            conflict_field="run_id",
        )
        self._upsert_rows(
            table=self._settings.telemetry_supabase_llm_calls_table,
            rows=batch.llm_calls,
            conflict_field="call_id",
        )
        self._upsert_rows(
            table=self._settings.telemetry_supabase_tool_calls_table,
            rows=batch.tool_calls,
            conflict_field="tool_call_id",
        )
        self._upsert_rows(
            table=self._settings.telemetry_supabase_stage_events_table,
            rows=batch.stage_events,
            conflict_field="event_id",
        )

    def _upsert_rows(
        self,
        *,
        table: str,
        rows: list[dict[str, Any]],
        conflict_field: str,
    ) -> None:
        if not rows:
            return

        endpoint = self._build_endpoint(table=table, conflict_field=conflict_field)
        encoded_payload = json.dumps(rows, ensure_ascii=False).encode("utf-8")
        request = Request(
            endpoint,
            data=encoded_payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "apikey": self._settings.supabase_service_role_key,
                "Authorization": f"Bearer {self._settings.supabase_service_role_key}",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self._settings.telemetry_supabase_timeout_seconds):
                return
        except HTTPError as exc:
            response_body = _read_http_error_body(exc)
            self._logger.exception(
                "telemetry.supabase.persist_failed",
                extra={
                    "telemetry_event": "telemetry.supabase.persist_failed",
                    "storage": {
                        "backend": "supabase",
                        "table": table,
                        "endpoint": sanitize_url(endpoint),
                    },
                    "http_status": getattr(exc, "code", None),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "response_body_preview": _preview_json_text(
                        response_body,
                        max_chars=self._settings.log_internal_max_body_chars,
                    ),
                },
            )
            raise
        except URLError as exc:
            self._logger.exception(
                "telemetry.supabase.request_failed",
                extra={
                    "telemetry_event": "telemetry.supabase.request_failed",
                    "storage": {
                        "backend": "supabase",
                        "table": table,
                        "endpoint": sanitize_url(endpoint),
                    },
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            raise

    def _build_endpoint(self, *, table: str, conflict_field: str) -> str:
        base_url = self._settings.supabase_url.strip().rstrip("/")
        table_name = quote(table.strip(), safe="_")
        conflict = quote(conflict_field.strip(), safe="_")
        return f"{base_url}/rest/v1/{table_name}?on_conflict={conflict}"


class TelemetryCollector:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: SupabaseTelemetryRepository | None = None,
    ) -> None:
        now = _utcnow()
        self._settings = settings
        self._repository = repository
        self._logger = logging.getLogger(__name__)
        self._run = {
            "run_id": uuid4().hex,
            "created_at": _isoformat(now),
            "updated_at": _isoformat(now),
            "request_id": get_request_id(),
            "trace_id": get_trace_id(),
            "conversation_id": None,
            "agent": None,
            "entrypoint": None,
            "flow": None,
            "engine": None,
            "contexto": None,
            "idioma": None,
            "intencao": None,
            "pipeline": None,
            "handler": None,
            "status": None,
            "http_method": None,
            "http_path": None,
            "http_status_code": None,
            "client_ip": None,
            "query_json": {},
            "started_at": _isoformat(now),
            "finished_at": None,
            "duration_ms": None,
            "timeout": False,
            "warnings_count": 0,
            "precisa_revisao": False,
            "fallback_count": 0,
            "rag_used": False,
            "rag_docs_count": 0,
            "llm_calls_count": 0,
            "tool_calls_count": 0,
            "stage_events_count": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": None,
            "error_type": None,
            "error_message": None,
            "metadata_json": {},
        }
        self._llm_calls: list[dict[str, Any]] = []
        self._tool_calls: list[dict[str, Any]] = []
        self._stage_events: list[dict[str, Any]] = []

    def set_request_context(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, Any],
        client_ip: str | None,
        contexto: str | None,
    ) -> None:
        self.update_run(
            http_method=method.upper(),
            http_path=path,
            entrypoint=path,
            client_ip=client_ip,
            contexto=contexto,
            query_json=_json_safe(query),
        )

    def update_run(self, **fields: Any) -> None:
        metadata = fields.pop("metadata_json", None)
        for key, value in fields.items():
            if value is not None:
                self._run[key] = _json_safe(value)
        if isinstance(metadata, dict) and metadata:
            current_metadata = self._run.get("metadata_json")
            if not isinstance(current_metadata, dict):
                current_metadata = {}
            current_metadata.update(_json_safe(metadata))
            self._run["metadata_json"] = current_metadata
        self._run["updated_at"] = _isoformat(_utcnow())

    def finalize_request(
        self,
        *,
        status_code: int,
        duration_ms: float,
        timeout: bool,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        status = self._run.get("status") or _resolve_http_status(status_code=status_code, error_type=error_type)
        self.update_run(
            http_status_code=status_code,
            duration_ms=round(duration_ms, 4),
            timeout=bool(timeout),
            finished_at=_isoformat(_utcnow()),
            status=status,
            error_type=error_type,
            error_message=error_message,
        )

    def add_llm_call(self, **fields: Any) -> None:
        record = {
            "call_id": uuid4().hex,
            "run_id": self._run["run_id"],
            "request_id": self._run["request_id"],
            "trace_id": self._run["trace_id"],
            "created_at": _isoformat(_utcnow()),
            "provider": fields.get("provider"),
            "operation": fields.get("operation"),
            "model": fields.get("model"),
            "provider_response_id": fields.get("provider_response_id"),
            "status": fields.get("status"),
            "timeout": bool(fields.get("timeout", False)),
            "duration_ms": _rounded_float(fields.get("duration_ms")),
            "input_tokens": _coalesce_int(fields.get("input_tokens")),
            "output_tokens": _coalesce_int(fields.get("output_tokens")),
            "total_tokens": _coalesce_int(fields.get("total_tokens")),
            "cost_usd": _rounded_cost(fields.get("cost_usd")),
            "prompt_chars": _coalesce_int(fields.get("prompt_chars")),
            "output_chars": _coalesce_int(fields.get("output_chars")),
            "error_type": fields.get("error_type"),
            "error_message": fields.get("error_message"),
            "prompt_preview_masked": fields.get("prompt_preview_masked"),
            "response_preview_masked": fields.get("response_preview_masked"),
            "metadata_json": _json_safe(fields.get("metadata_json") or {}),
        }
        self._llm_calls.append(record)
        self._run["llm_calls_count"] += 1
        self._run["total_input_tokens"] += max(0, record["input_tokens"] or 0)
        self._run["total_output_tokens"] += max(0, record["output_tokens"] or 0)
        self._run["total_tokens"] += max(0, record["total_tokens"] or 0)
        if record["cost_usd"] is not None:
            current = self._run.get("total_cost_usd")
            self._run["total_cost_usd"] = round(float(current or 0.0) + float(record["cost_usd"]), 10)
        self._run["updated_at"] = _isoformat(_utcnow())

    def add_tool_call(self, **fields: Any) -> None:
        record = {
            "tool_call_id": uuid4().hex,
            "run_id": self._run["run_id"],
            "request_id": self._run["request_id"],
            "trace_id": self._run["trace_id"],
            "created_at": _isoformat(_utcnow()),
            "tool_name": fields.get("tool_name"),
            "status": fields.get("status"),
            "duration_ms": _rounded_float(fields.get("duration_ms")),
            "timeout": bool(fields.get("timeout", False)),
            "error_type": fields.get("error_type"),
            "warnings_count": _coalesce_int(fields.get("warnings_count")),
            "precisa_revisao": bool(fields.get("precisa_revisao", False)),
            "metadata_json": _json_safe(fields.get("metadata_json") or {}),
        }
        self._tool_calls.append(record)
        self._run["tool_calls_count"] += 1
        if record["precisa_revisao"]:
            self._run["precisa_revisao"] = True
        self._run["updated_at"] = _isoformat(_utcnow())

    def add_stage_event(self, **fields: Any) -> None:
        record = {
            "event_id": uuid4().hex,
            "run_id": self._run["run_id"],
            "request_id": self._run["request_id"],
            "trace_id": self._run["trace_id"],
            "created_at": _isoformat(_utcnow()),
            "event_type": fields.get("event_type"),
            "name": fields.get("name"),
            "status": fields.get("status"),
            "duration_ms": _rounded_float(fields.get("duration_ms")),
            "timeout": bool(fields.get("timeout", False)),
            "flow": fields.get("flow"),
            "engine": fields.get("engine"),
            "reason": fields.get("reason"),
            "used": fields.get("used"),
            "documents_count": _coalesce_int(fields.get("documents_count")),
            "metadata_json": _json_safe(fields.get("metadata_json") or {}),
        }
        self._stage_events.append(record)
        self._run["stage_events_count"] += 1
        if record["event_type"] == "chat_fallback":
            self._run["fallback_count"] += 1
        if record["event_type"] == "chat_rag" and bool(record["used"]):
            self._run["rag_used"] = True
            self._run["rag_docs_count"] += max(0, record["documents_count"] or 0)
        if record["event_type"] == "chat_flow" and isinstance(record["metadata_json"], dict):
            self.update_run(
                flow=record["flow"] or record["name"],
                engine=record["engine"],
                intencao=record["metadata_json"].get("intencao"),
                pipeline=record["metadata_json"].get("pipeline"),
                handler=record["metadata_json"].get("handler"),
            )
        self._run["updated_at"] = _isoformat(_utcnow())

    def build_batch(self) -> TelemetryBatch:
        return TelemetryBatch(
            agent_run=_json_safe(self._run),
            llm_calls=_json_safe(self._llm_calls),
            tool_calls=_json_safe(self._tool_calls),
            stage_events=_json_safe(self._stage_events),
        )

    def flush(self) -> None:
        if self._repository is None or not self._repository.enabled:
            return
        try:
            self._repository.persist(self.build_batch())
        except Exception:
            self._logger.exception(
                "telemetry.flush_failed",
                extra={
                    "telemetry_event": "telemetry.flush_failed",
                    "run_id": self._run.get("run_id"),
                    "request_id": self._run.get("request_id"),
                    "trace_id": self._run.get("trace_id"),
                },
            )


def start_request_telemetry(
    *,
    settings: Settings | None,
    method: str,
    path: str,
    query: dict[str, Any],
    client_ip: str | None,
    contexto: str | None,
) -> Token[Any | None] | None:
    settings = settings or get_settings()
    repository = get_supabase_telemetry_repository()
    if not settings.telemetry_enabled or not repository.enabled:
        return None
    collector = TelemetryCollector(settings=settings, repository=repository)
    collector.set_request_context(
        method=method,
        path=path,
        query=query,
        client_ip=client_ip,
        contexto=contexto,
    )
    return set_telemetry_collector(collector)


async def finalize_request_telemetry(
    *,
    status_code: int,
    duration_ms: float,
    timeout: bool,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    collector = get_telemetry_collector()
    if collector is None:
        return
    collector.finalize_request(
        status_code=status_code,
        duration_ms=duration_ms,
        timeout=timeout,
        error_type=error_type,
        error_message=error_message,
    )
    await run_in_threadpool(collector.flush)


def set_agent_run_metadata(**fields: Any) -> None:
    collector = get_telemetry_collector()
    if collector is None:
        return
    collector.update_run(**fields)


def record_llm_call(**fields: Any) -> None:
    collector = get_telemetry_collector()
    if collector is None:
        return
    collector.add_llm_call(**fields)


def record_tool_call(**fields: Any) -> None:
    collector = get_telemetry_collector()
    if collector is None:
        return
    collector.add_tool_call(**fields)


def record_stage_event(**fields: Any) -> None:
    collector = get_telemetry_collector()
    if collector is None:
        return
    collector.add_stage_event(**fields)


@lru_cache(maxsize=1)
def get_supabase_telemetry_repository() -> SupabaseTelemetryRepository:
    return SupabaseTelemetryRepository(settings=get_settings())


def _resolve_http_status(*, status_code: int, error_type: str | None) -> str:
    if error_type or status_code >= 500:
        return "erro"
    if status_code >= 400:
        return "falha_cliente"
    return "sucesso"


def _preview_json_text(raw_body: str | None, *, max_chars: int) -> Any | None:
    if not raw_body:
        return None
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        return raw_body[:max_chars]
    return preview_json(parsed, max_chars=max_chars)


def _read_http_error_body(error: HTTPError) -> str | None:
    try:
        return error.read().decode("utf-8")
    except Exception:
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


def _rounded_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _rounded_cost(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 10)
    except (TypeError, ValueError):
        return None


def _coalesce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None

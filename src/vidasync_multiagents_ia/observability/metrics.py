from collections import defaultdict
from dataclasses import dataclass
from threading import Lock

from vidasync_multiagents_ia.observability.telemetry import record_stage_event


@dataclass(slots=True)
class _HistogramBucket:
    count: int = 0
    total_ms: float = 0.0


@dataclass(slots=True)
class _SumBucket:
    count: int = 0
    total: float = 0.0


class _MetricsStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._http_requests = defaultdict(int)
        self._http_duration = defaultdict(_HistogramBucket)
        self._http_timeouts = defaultdict(int)
        self._external_requests = defaultdict(int)
        self._external_duration = defaultdict(_HistogramBucket)
        self._external_timeouts = defaultdict(int)
        self._chat_flow_requests = defaultdict(int)
        self._chat_flow_duration = defaultdict(_HistogramBucket)
        self._chat_stage_duration = defaultdict(_HistogramBucket)
        self._chat_timeouts = defaultdict(int)
        self._chat_tool_requests = defaultdict(int)
        self._chat_tool_duration = defaultdict(_HistogramBucket)
        self._chat_tool_failures = defaultdict(int)
        self._chat_fallbacks = defaultdict(int)
        self._chat_rag_requests = defaultdict(int)
        self._chat_rag_docs = defaultdict(_SumBucket)
        self._ai_router_requests = defaultdict(int)
        self._ai_router_duration = defaultdict(_HistogramBucket)
        self._ai_router_timeouts = defaultdict(int)

    def record_http(self, *, method: str, path: str, status_code: int, duration_ms: float) -> None:
        status = str(status_code)
        key = (method.upper(), path, status)
        with self._lock:
            self._http_requests[key] += 1
            bucket = self._http_duration[key]
            bucket.count += 1
            bucket.total_ms += float(duration_ms)

    def record_http_timeout(self, *, method: str, path: str) -> None:
        key = (method.upper(), path)
        with self._lock:
            self._http_timeouts[key] += 1

    def record_external(self, *, client: str, operation: str, status: str, duration_ms: float) -> None:
        key = (client, operation, status)
        with self._lock:
            self._external_requests[key] += 1
            bucket = self._external_duration[key]
            bucket.count += 1
            bucket.total_ms += float(duration_ms)

    def record_external_timeout(self, *, client: str, operation: str) -> None:
        key = (client, operation)
        with self._lock:
            self._external_timeouts[key] += 1

    def record_chat_flow(
        self,
        *,
        flow: str,
        engine: str,
        intencao: str,
        pipeline: str,
        handler: str,
        status: str,
        duration_ms: float,
    ) -> None:
        key = (flow, engine, intencao, pipeline, handler, status)
        with self._lock:
            self._chat_flow_requests[key] += 1
            bucket = self._chat_flow_duration[key]
            bucket.count += 1
            bucket.total_ms += float(duration_ms)

    def record_chat_stage_duration(self, *, engine: str, stage: str, status: str, duration_ms: float) -> None:
        key = (engine, stage, status)
        with self._lock:
            bucket = self._chat_stage_duration[key]
            bucket.count += 1
            bucket.total_ms += float(duration_ms)

    def record_chat_timeout(self, *, flow: str, stage: str) -> None:
        key = (flow, stage)
        with self._lock:
            self._chat_timeouts[key] += 1

    def record_chat_tool_execution(self, *, tool: str, status: str, duration_ms: float) -> None:
        key = (tool, status)
        with self._lock:
            self._chat_tool_requests[key] += 1
            bucket = self._chat_tool_duration[key]
            bucket.count += 1
            bucket.total_ms += float(duration_ms)

    def record_chat_tool_failure(self, *, tool: str, error_type: str) -> None:
        key = (tool, error_type)
        with self._lock:
            self._chat_tool_failures[key] += 1

    def record_chat_fallback(self, *, flow: str, reason: str) -> None:
        key = (flow, reason)
        with self._lock:
            self._chat_fallbacks[key] += 1

    def record_chat_rag_usage(self, *, context: str, used: bool, documents_count: int) -> None:
        key = (context, "true" if used else "false")
        with self._lock:
            self._chat_rag_requests[key] += 1
            bucket = self._chat_rag_docs[key]
            bucket.count += 1
            bucket.total += float(max(0, documents_count))

    def record_ai_router(self, *, contexto: str, status: str, duration_ms: float) -> None:
        key = (contexto, status)
        with self._lock:
            self._ai_router_requests[key] += 1
            bucket = self._ai_router_duration[key]
            bucket.count += 1
            bucket.total_ms += float(duration_ms)

    def record_ai_router_timeout(self, *, contexto: str) -> None:
        with self._lock:
            self._ai_router_timeouts[contexto] += 1

    def render_prometheus(self) -> str:
        # /**** Formato Prometheus para troubleshooting operacional local e integracao com dashboards. ****/
        with self._lock:
            lines: list[str] = []

            lines.append("# HELP vidasync_http_requests_total Total de requests HTTP recebidos.")
            lines.append("# TYPE vidasync_http_requests_total counter")
            for (method, path, status), value in sorted(self._http_requests.items()):
                lines.append(
                    'vidasync_http_requests_total{method="%s",path="%s",status="%s"} %d'
                    % (_escape_label(method), _escape_label(path), _escape_label(status), value)
                )

            lines.append("# HELP vidasync_http_request_duration_ms_sum Soma de duracao de requests HTTP em ms.")
            lines.append("# TYPE vidasync_http_request_duration_ms_sum counter")
            lines.append("# HELP vidasync_http_request_duration_ms_count Quantidade de requests HTTP com duracao.")
            lines.append("# TYPE vidasync_http_request_duration_ms_count counter")
            for (method, path, status), bucket in sorted(self._http_duration.items()):
                labels = 'method="%s",path="%s",status="%s"' % (
                    _escape_label(method),
                    _escape_label(path),
                    _escape_label(status),
                )
                lines.append(f"vidasync_http_request_duration_ms_sum{{{labels}}} {bucket.total_ms:.6f}")
                lines.append(f"vidasync_http_request_duration_ms_count{{{labels}}} {bucket.count}")

            lines.append("# HELP vidasync_http_timeouts_total Total de timeouts por endpoint HTTP.")
            lines.append("# TYPE vidasync_http_timeouts_total counter")
            for (method, path), value in sorted(self._http_timeouts.items()):
                lines.append(
                    'vidasync_http_timeouts_total{method="%s",path="%s"} %d'
                    % (_escape_label(method), _escape_label(path), value)
                )

            lines.append("# HELP vidasync_external_requests_total Total de requests para APIs externas.")
            lines.append("# TYPE vidasync_external_requests_total counter")
            for (client, operation, status), value in sorted(self._external_requests.items()):
                lines.append(
                    'vidasync_external_requests_total{client="%s",operation="%s",status="%s"} %d'
                    % (
                        _escape_label(client),
                        _escape_label(operation),
                        _escape_label(status),
                        value,
                    )
                )

            lines.append("# HELP vidasync_external_request_duration_ms_sum Soma de duracao das chamadas externas em ms.")
            lines.append("# TYPE vidasync_external_request_duration_ms_sum counter")
            lines.append("# HELP vidasync_external_request_duration_ms_count Quantidade de chamadas externas com duracao.")
            lines.append("# TYPE vidasync_external_request_duration_ms_count counter")
            for (client, operation, status), bucket in sorted(self._external_duration.items()):
                labels = 'client="%s",operation="%s",status="%s"' % (
                    _escape_label(client),
                    _escape_label(operation),
                    _escape_label(status),
                )
                lines.append(f"vidasync_external_request_duration_ms_sum{{{labels}}} {bucket.total_ms:.6f}")
                lines.append(f"vidasync_external_request_duration_ms_count{{{labels}}} {bucket.count}")

            lines.append("# HELP vidasync_external_timeouts_total Total de timeouts por cliente externo.")
            lines.append("# TYPE vidasync_external_timeouts_total counter")
            for (client, operation), value in sorted(self._external_timeouts.items()):
                lines.append(
                    'vidasync_external_timeouts_total{client="%s",operation="%s"} %d'
                    % (_escape_label(client), _escape_label(operation), value)
                )

            lines.append("# HELP vidasync_chat_flow_requests_total Total de execucoes do fluxo conversacional.")
            lines.append("# TYPE vidasync_chat_flow_requests_total counter")
            for (flow, engine, intencao, pipeline, handler, status), value in sorted(self._chat_flow_requests.items()):
                lines.append(
                    'vidasync_chat_flow_requests_total{flow="%s",engine="%s",intencao="%s",pipeline="%s",handler="%s",status="%s"} %d'
                    % (
                        _escape_label(flow),
                        _escape_label(engine),
                        _escape_label(intencao),
                        _escape_label(pipeline),
                        _escape_label(handler),
                        _escape_label(status),
                        value,
                    )
                )

            lines.append("# HELP vidasync_chat_flow_duration_ms_sum Soma de duracao dos fluxos de chat em ms.")
            lines.append("# TYPE vidasync_chat_flow_duration_ms_sum counter")
            lines.append("# HELP vidasync_chat_flow_duration_ms_count Quantidade de fluxos de chat com duracao.")
            lines.append("# TYPE vidasync_chat_flow_duration_ms_count counter")
            for (flow, engine, intencao, pipeline, handler, status), bucket in sorted(self._chat_flow_duration.items()):
                labels = 'flow="%s",engine="%s",intencao="%s",pipeline="%s",handler="%s",status="%s"' % (
                    _escape_label(flow),
                    _escape_label(engine),
                    _escape_label(intencao),
                    _escape_label(pipeline),
                    _escape_label(handler),
                    _escape_label(status),
                )
                lines.append(f"vidasync_chat_flow_duration_ms_sum{{{labels}}} {bucket.total_ms:.6f}")
                lines.append(f"vidasync_chat_flow_duration_ms_count{{{labels}}} {bucket.count}")

            lines.append("# HELP vidasync_chat_stage_duration_ms_sum Soma de duracao por etapa do chat em ms.")
            lines.append("# TYPE vidasync_chat_stage_duration_ms_sum counter")
            lines.append("# HELP vidasync_chat_stage_duration_ms_count Quantidade de duracoes por etapa do chat.")
            lines.append("# TYPE vidasync_chat_stage_duration_ms_count counter")
            for (engine, stage, status), bucket in sorted(self._chat_stage_duration.items()):
                labels = 'engine="%s",stage="%s",status="%s"' % (
                    _escape_label(engine),
                    _escape_label(stage),
                    _escape_label(status),
                )
                lines.append(f"vidasync_chat_stage_duration_ms_sum{{{labels}}} {bucket.total_ms:.6f}")
                lines.append(f"vidasync_chat_stage_duration_ms_count{{{labels}}} {bucket.count}")

            lines.append("# HELP vidasync_chat_timeouts_total Total de timeouts no fluxo de chat por etapa.")
            lines.append("# TYPE vidasync_chat_timeouts_total counter")
            for (flow, stage), value in sorted(self._chat_timeouts.items()):
                lines.append(
                    'vidasync_chat_timeouts_total{flow="%s",stage="%s"} %d'
                    % (_escape_label(flow), _escape_label(stage), value)
                )

            lines.append("# HELP vidasync_chat_tool_requests_total Total de execucoes de tools no chat.")
            lines.append("# TYPE vidasync_chat_tool_requests_total counter")
            for (tool, status), value in sorted(self._chat_tool_requests.items()):
                lines.append(
                    'vidasync_chat_tool_requests_total{tool="%s",status="%s"} %d'
                    % (_escape_label(tool), _escape_label(status), value)
                )

            lines.append("# HELP vidasync_chat_tool_duration_ms_sum Soma de duracao de tools de chat em ms.")
            lines.append("# TYPE vidasync_chat_tool_duration_ms_sum counter")
            lines.append("# HELP vidasync_chat_tool_duration_ms_count Quantidade de duracao de tools de chat.")
            lines.append("# TYPE vidasync_chat_tool_duration_ms_count counter")
            for (tool, status), bucket in sorted(self._chat_tool_duration.items()):
                labels = 'tool="%s",status="%s"' % (_escape_label(tool), _escape_label(status))
                lines.append(f"vidasync_chat_tool_duration_ms_sum{{{labels}}} {bucket.total_ms:.6f}")
                lines.append(f"vidasync_chat_tool_duration_ms_count{{{labels}}} {bucket.count}")

            lines.append("# HELP vidasync_chat_tool_failures_total Total de falhas de tool por tipo de erro.")
            lines.append("# TYPE vidasync_chat_tool_failures_total counter")
            for (tool, error_type), value in sorted(self._chat_tool_failures.items()):
                lines.append(
                    'vidasync_chat_tool_failures_total{tool="%s",error_type="%s"} %d'
                    % (_escape_label(tool), _escape_label(error_type), value)
                )

            lines.append("# HELP vidasync_chat_fallbacks_total Total de fallbacks aplicados no chat.")
            lines.append("# TYPE vidasync_chat_fallbacks_total counter")
            for (flow, reason), value in sorted(self._chat_fallbacks.items()):
                lines.append(
                    'vidasync_chat_fallbacks_total{flow="%s",reason="%s"} %d'
                    % (_escape_label(flow), _escape_label(reason), value)
                )

            lines.append("# HELP vidasync_chat_rag_requests_total Total de consultas com/sem uso de RAG no chat.")
            lines.append("# TYPE vidasync_chat_rag_requests_total counter")
            for (context, used), value in sorted(self._chat_rag_requests.items()):
                lines.append(
                    'vidasync_chat_rag_requests_total{context="%s",used="%s"} %d'
                    % (_escape_label(context), _escape_label(used), value)
                )

            lines.append("# HELP vidasync_chat_rag_documents_total Soma de documentos recuperados por consulta RAG.")
            lines.append("# TYPE vidasync_chat_rag_documents_total counter")
            lines.append("# HELP vidasync_chat_rag_documents_count Quantidade de consultas RAG com medicao.")
            lines.append("# TYPE vidasync_chat_rag_documents_count counter")
            for (context, used), bucket in sorted(self._chat_rag_docs.items()):
                labels = 'context="%s",used="%s"' % (_escape_label(context), _escape_label(used))
                lines.append(f"vidasync_chat_rag_documents_total{{{labels}}} {bucket.total:.6f}")
                lines.append(f"vidasync_chat_rag_documents_count{{{labels}}} {bucket.count}")

            lines.append("# HELP vidasync_ai_router_requests_total Total de execucoes por contexto no /ai/router.")
            lines.append("# TYPE vidasync_ai_router_requests_total counter")
            for (contexto, status), value in sorted(self._ai_router_requests.items()):
                lines.append(
                    'vidasync_ai_router_requests_total{contexto="%s",status="%s"} %d'
                    % (_escape_label(contexto), _escape_label(status), value)
                )

            lines.append("# HELP vidasync_ai_router_duration_ms_sum Soma de duracao por contexto no /ai/router.")
            lines.append("# TYPE vidasync_ai_router_duration_ms_sum counter")
            lines.append("# HELP vidasync_ai_router_duration_ms_count Quantidade de execucoes no /ai/router com duracao.")
            lines.append("# TYPE vidasync_ai_router_duration_ms_count counter")
            for (contexto, status), bucket in sorted(self._ai_router_duration.items()):
                labels = 'contexto="%s",status="%s"' % (_escape_label(contexto), _escape_label(status))
                lines.append(f"vidasync_ai_router_duration_ms_sum{{{labels}}} {bucket.total_ms:.6f}")
                lines.append(f"vidasync_ai_router_duration_ms_count{{{labels}}} {bucket.count}")

            lines.append("# HELP vidasync_ai_router_timeouts_total Total de timeouts por contexto no /ai/router.")
            lines.append("# TYPE vidasync_ai_router_timeouts_total counter")
            for contexto, value in sorted(self._ai_router_timeouts.items()):
                lines.append(
                    'vidasync_ai_router_timeouts_total{contexto="%s"} %d'
                    % (_escape_label(contexto), value)
                )

            return "\n".join(lines) + "\n"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


_metrics_store = _MetricsStore()


def record_http_request(*, method: str, path: str, status_code: int, duration_ms: float) -> None:
    _metrics_store.record_http(method=method, path=path, status_code=status_code, duration_ms=duration_ms)


def record_http_timeout(*, method: str, path: str) -> None:
    _metrics_store.record_http_timeout(method=method, path=path)


def record_external_request(*, client: str, operation: str, status: str, duration_ms: float) -> None:
    _metrics_store.record_external(client=client, operation=operation, status=status, duration_ms=duration_ms)
    record_stage_event(
        event_type="external_request",
        name=operation,
        status=status,
        duration_ms=duration_ms,
        metadata_json={"client": client},
    )


def record_external_timeout(*, client: str, operation: str) -> None:
    _metrics_store.record_external_timeout(client=client, operation=operation)


def record_chat_flow_execution(
    *,
    flow: str,
    engine: str,
    intencao: str,
    pipeline: str,
    handler: str,
    status: str,
    duration_ms: float,
) -> None:
    _metrics_store.record_chat_flow(
        flow=flow,
        engine=engine,
        intencao=intencao,
        pipeline=pipeline,
        handler=handler,
        status=status,
        duration_ms=duration_ms,
    )
    record_stage_event(
        event_type="chat_flow",
        name=flow,
        status=status,
        duration_ms=duration_ms,
        flow=flow,
        engine=engine,
        metadata_json={
            "intencao": intencao,
            "pipeline": pipeline,
            "handler": handler,
        },
    )


def record_chat_stage_duration(*, engine: str, stage: str, status: str, duration_ms: float) -> None:
    _metrics_store.record_chat_stage_duration(engine=engine, stage=stage, status=status, duration_ms=duration_ms)
    record_stage_event(
        event_type="chat_stage",
        name=stage,
        status=status,
        duration_ms=duration_ms,
        engine=engine,
    )


def record_chat_timeout(*, flow: str, stage: str) -> None:
    _metrics_store.record_chat_timeout(flow=flow, stage=stage)
    record_stage_event(
        event_type="chat_timeout",
        name=stage,
        status="timeout",
        timeout=True,
        flow=flow,
    )


def record_chat_tool_execution(*, tool: str, status: str, duration_ms: float) -> None:
    _metrics_store.record_chat_tool_execution(tool=tool, status=status, duration_ms=duration_ms)


def record_chat_tool_failure(*, tool: str, error_type: str) -> None:
    _metrics_store.record_chat_tool_failure(tool=tool, error_type=error_type)


def record_chat_fallback(*, flow: str, reason: str) -> None:
    _metrics_store.record_chat_fallback(flow=flow, reason=reason)
    record_stage_event(
        event_type="chat_fallback",
        name=flow,
        status="fallback",
        flow=flow,
        reason=reason,
    )


def record_chat_rag_usage(*, context: str, used: bool, documents_count: int) -> None:
    _metrics_store.record_chat_rag_usage(context=context, used=used, documents_count=documents_count)
    record_stage_event(
        event_type="chat_rag",
        name=context,
        status="used" if used else "not_used",
        used=used,
        documents_count=documents_count,
    )


def record_ai_router_request(*, contexto: str, status: str, duration_ms: float) -> None:
    _metrics_store.record_ai_router(contexto=contexto, status=status, duration_ms=duration_ms)
    record_stage_event(
        event_type="ai_router_request",
        name=contexto,
        status=status,
        duration_ms=duration_ms,
    )


def record_ai_router_timeout(*, contexto: str) -> None:
    _metrics_store.record_ai_router_timeout(contexto=contexto)
    record_stage_event(
        event_type="ai_router_timeout",
        name=contexto,
        status="timeout",
        timeout=True,
    )


def render_metrics_prometheus() -> str:
    return _metrics_store.render_prometheus()

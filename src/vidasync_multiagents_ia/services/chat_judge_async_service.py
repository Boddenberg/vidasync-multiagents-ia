import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability import set_agent_run_metadata
from vidasync_multiagents_ia.observability.context import (
    reset_request_id,
    reset_telemetry_collector,
    reset_trace_id,
    set_request_id,
    set_telemetry_collector,
    set_trace_id,
)
from vidasync_multiagents_ia.observability.telemetry import (
    TelemetryCollector,
    get_supabase_telemetry_repository,
)
from vidasync_multiagents_ia.schemas import (
    ChatJudgeEvaluationInput,
    ChatJudgeExecutionRef,
    ChatJudgeTrackingRecord,
    OpenAIChatResponse,
)
from vidasync_multiagents_ia.services.chat_judge_service import ChatJudgeService
from vidasync_multiagents_ia.services.chat_judge_supabase_repository import ChatJudgeSupabaseRepository
from vidasync_multiagents_ia.services.chat_judge_tracking_mapper import (
    build_completed_chat_judge_tracking_record,
    build_failed_chat_judge_tracking_record,
    build_pending_chat_judge_tracking_record,
)


@dataclass(slots=True)
class PreparedChatJudgeEvaluation:
    execution: ChatJudgeExecutionRef
    pending_record: ChatJudgeTrackingRecord
    judge_request: ChatJudgeEvaluationInput


@dataclass(slots=True)
class _BackgroundTelemetryScope:
    collector: TelemetryCollector
    request_token: Any
    trace_token: Any
    telemetry_token: Any


class ChatJudgeAsyncService:
    def __init__(
        self,
        *,
        settings: Settings,
        judge_service: ChatJudgeService | None = None,
        repository: ChatJudgeSupabaseRepository | None = None,
        telemetry_repository: Any | None = None,
    ) -> None:
        self._settings = settings
        self._judge_service = judge_service or ChatJudgeService(settings=settings)
        self._repository = repository or ChatJudgeSupabaseRepository(settings=settings)
        self._telemetry_repository = telemetry_repository
        self._logger = logging.getLogger(__name__)

    @property
    def enabled_for_chat(self) -> bool:
        return (
            self._settings.chat_judge_enabled
            and self._settings.chat_judge_chat_async_enabled
            and self._repository.enabled
        )

    def prepare_chat_response_evaluation(
        self,
        *,
        prompt: str,
        response: OpenAIChatResponse,
        conversation_id: str | None,
        usar_memoria: bool,
        metadados_conversa: dict[str, Any] | None,
        plano_anexo_presente: bool,
        refeicao_anexo_presente: bool,
        source_duration_ms: float | None,
    ) -> PreparedChatJudgeEvaluation | None:
        if not self.enabled_for_chat:
            self._logger.info(
                "Chat judge async evaluation skipped.",
                extra={
                    "judge_event": "chat_judge_async.skipped",
                    "judge_enabled": self._settings.chat_judge_enabled,
                    "chat_async_enabled": self._settings.chat_judge_chat_async_enabled,
                    "supabase_enabled": self._repository.enabled,
                },
            )
            return None

        normalized_metadata = _normalize_metadata(metadados_conversa)
        resolved_conversation_id = response.conversation_id or conversation_id
        request_id = _extract_metadata_text(normalized_metadata, "request_id")
        message_id = _extract_metadata_text(normalized_metadata, "message_id")
        user_id = _extract_metadata_text(normalized_metadata, "user_id")
        routing_payload = response.roteamento.model_dump(mode="json") if response.roteamento else None
        intent_payload = (
            response.intencao_detectada.model_dump(mode="json") if response.intencao_detectada else None
        )
        memory_payload = response.memoria.model_dump(mode="json") if response.memoria else None

        pending_record = build_pending_chat_judge_tracking_record(
            source_model=response.model,
            source_prompt=prompt,
            source_response=response.response,
            source_duration_ms=source_duration_ms,
            request_id=request_id,
            conversation_id=resolved_conversation_id,
            message_id=message_id,
            user_id=user_id,
            idioma="pt-BR",
            intencao=response.intencao_detectada.intencao if response.intencao_detectada else None,
            pipeline=response.roteamento.pipeline if response.roteamento else None,
            handler=response.roteamento.handler if response.roteamento else None,
            source_metadata={
                "metadados_conversa": normalized_metadata,
                "usar_memoria": usar_memoria,
                "plano_anexo_presente": plano_anexo_presente,
                "refeicao_anexo_presente": refeicao_anexo_presente,
                "intencao_detectada": intent_payload,
                "roteamento": routing_payload,
                "memoria": memory_payload,
            },
        )
        identifiers = _build_identifiers(pending_record)

        self._logger.info(
            "Chat judge async evaluation queued.",
            extra={
                "judge_event": "chat_judge_async.started",
                "identifiers": identifiers,
                "source": {
                    "feature": pending_record.feature,
                    "pipeline": pending_record.pipeline,
                    "handler": pending_record.handler,
                },
            },
        )

        try:
            self._repository.upsert(pending_record)
        except ServiceError:
            self._logger.exception(
                "Chat judge async pending persistence failed.",
                extra={
                    "judge_event": "chat_judge_async.pending_failed",
                    "identifiers": identifiers,
                },
            )
            return None

        judge_request = ChatJudgeEvaluationInput(
            user_prompt=prompt,
            assistant_response=response.response,
            conversation_id=resolved_conversation_id,
            message_id=message_id,
            request_id=request_id,
            idioma="pt-BR",
            intencao=response.intencao_detectada.intencao if response.intencao_detectada else None,
            pipeline=response.roteamento.pipeline if response.roteamento else None,
            handler=response.roteamento.handler if response.roteamento else None,
            metadados_conversa=normalized_metadata,
            roteamento_metadados=response.roteamento.metadados if response.roteamento else {},
            source_context={
                "intencao_detectada": intent_payload,
                "roteamento": routing_payload,
                "memoria": memory_payload,
            },
        )

        return PreparedChatJudgeEvaluation(
            execution=ChatJudgeExecutionRef(
                evaluation_id=pending_record.evaluation_id,
                status="pending",
            ),
            pending_record=pending_record,
            judge_request=judge_request,
        )

    def execute_prepared_chat_response_evaluation(
        self,
        prepared: PreparedChatJudgeEvaluation,
    ) -> str:
        pending_record = prepared.pending_record
        identifiers = _build_identifiers(pending_record)
        telemetry_scope = self._start_background_telemetry(pending_record)
        started = perf_counter()

        try:
            judge_result = self._judge_service.evaluate(prepared.judge_request)
            judge_duration_ms = round((perf_counter() - started) * 1000.0, 4)
            completed_record = build_completed_chat_judge_tracking_record(
                pending_record,
                judge_result,
                judge_duration_ms=judge_duration_ms,
            )
            self._repository.upsert(completed_record)
            self._logger.info(
                "Chat judge async evaluation completed.",
                extra={
                    "judge_event": "chat_judge_async.completed",
                    "identifiers": identifiers,
                    "result": {
                        "judge_status": completed_record.judge_status,
                        "overall_score": completed_record.judge_overall_score,
                        "decision": completed_record.judge_decision,
                    },
                },
            )
            self._finalize_background_telemetry(
                telemetry_scope,
                status_code=200,
                duration_ms=judge_duration_ms,
            )
            return completed_record.evaluation_id
        except Exception as exc:
            judge_duration_ms = round((perf_counter() - started) * 1000.0, 4)
            failed_record = build_failed_chat_judge_tracking_record(
                pending_record,
                judge_model=self._settings.chat_judge_model,
                error_message=str(exc),
                judge_duration_ms=judge_duration_ms,
            )
            try:
                self._repository.upsert(failed_record)
            except ServiceError:
                self._logger.exception(
                    "Chat judge async failure persistence failed.",
                    extra={
                        "judge_event": "chat_judge_async.failure_persist_failed",
                        "identifiers": identifiers,
                    },
                )

            self._logger.exception(
                "Chat judge async evaluation failed.",
                extra={
                    "judge_event": "chat_judge_async.failed",
                    "identifiers": identifiers,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            self._finalize_background_telemetry(
                telemetry_scope,
                status_code=500,
                duration_ms=judge_duration_ms,
                error=exc,
            )
            return failed_record.evaluation_id

    def evaluate_chat_response(
        self,
        *,
        prompt: str,
        response: OpenAIChatResponse,
        conversation_id: str | None,
        usar_memoria: bool,
        metadados_conversa: dict[str, Any] | None,
        plano_anexo_presente: bool,
        refeicao_anexo_presente: bool,
        source_duration_ms: float | None,
    ) -> str | None:
        prepared = self.prepare_chat_response_evaluation(
            prompt=prompt,
            response=response,
            conversation_id=conversation_id,
            usar_memoria=usar_memoria,
            metadados_conversa=metadados_conversa,
            plano_anexo_presente=plano_anexo_presente,
            refeicao_anexo_presente=refeicao_anexo_presente,
            source_duration_ms=source_duration_ms,
        )
        if prepared is None:
            return None
        return self.execute_prepared_chat_response_evaluation(prepared)

    def _start_background_telemetry(
        self,
        pending_record: ChatJudgeTrackingRecord,
    ) -> _BackgroundTelemetryScope | None:
        repository = self._telemetry_repository or get_supabase_telemetry_repository()
        if not getattr(repository, "enabled", False):
            return None

        request_id = pending_record.request_id or pending_record.evaluation_id
        trace_id = request_id
        request_token = set_request_id(request_id)
        trace_token = set_trace_id(trace_id)
        collector = TelemetryCollector(settings=self._settings, repository=repository)
        collector.set_request_context(
            method="BACKGROUND",
            path="/v1/openai/chat/judge_async",
            query={},
            client_ip=None,
            contexto="chat_judge",
        )
        telemetry_token = set_telemetry_collector(collector)
        set_agent_run_metadata(
            agent="chat_judge_async",
            flow="chat_judge_async",
            engine="background",
            conversation_id=pending_record.conversation_id,
            contexto="chat_judge",
            status="em_andamento",
            intencao=pending_record.intencao,
            pipeline=pending_record.pipeline,
            handler=pending_record.handler,
            metadata_json={
                "evaluation_id": pending_record.evaluation_id,
                "feature": pending_record.feature,
                "source_model": pending_record.source_model,
                "message_id": pending_record.message_id,
            },
        )
        return _BackgroundTelemetryScope(
            collector=collector,
            request_token=request_token,
            trace_token=trace_token,
            telemetry_token=telemetry_token,
        )

    def _finalize_background_telemetry(
        self,
        scope: _BackgroundTelemetryScope | None,
        *,
        status_code: int,
        duration_ms: float,
        error: Exception | None = None,
    ) -> None:
        if scope is None:
            return
        try:
            scope.collector.update_run(status="sucesso" if status_code < 400 else "erro")
            scope.collector.finalize_request(
                status_code=status_code,
                duration_ms=duration_ms,
                timeout=_is_timeout_exception(error) if error is not None else False,
                error_type=type(error).__name__ if error is not None else None,
                error_message=str(error) if error is not None else None,
            )
            scope.collector.flush()
        finally:
            reset_telemetry_collector(scope.telemetry_token)
            reset_trace_id(scope.trace_token)
            reset_request_id(scope.request_token)


def _normalize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    return {str(key): value for key, value in metadata.items()}


def _extract_metadata_text(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_identifiers(record: ChatJudgeTrackingRecord) -> dict[str, str | None]:
    return {
        "evaluation_id": record.evaluation_id,
        "request_id": record.request_id,
        "conversation_id": record.conversation_id,
        "message_id": record.message_id,
    }


def _is_timeout_exception(exc: Exception | None) -> bool:
    current: BaseException | None = exc
    while current is not None:
        name = current.__class__.__name__.lower()
        message = str(current).lower()
        if "timeout" in name or "timed out" in message or "timeout" in message:
            return True
        current = current.__cause__ or current.__context__
    return False

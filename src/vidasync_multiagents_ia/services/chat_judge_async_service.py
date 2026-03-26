import logging
from time import perf_counter
from typing import Any

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import ChatJudgeEvaluationInput, OpenAIChatResponse
from vidasync_multiagents_ia.services.chat_judge_service import ChatJudgeService
from vidasync_multiagents_ia.services.chat_judge_supabase_repository import ChatJudgeSupabaseRepository
from vidasync_multiagents_ia.services.chat_judge_tracking_mapper import (
    build_completed_chat_judge_tracking_record,
    build_failed_chat_judge_tracking_record,
    build_pending_chat_judge_tracking_record,
)


class ChatJudgeAsyncService:
    def __init__(
        self,
        *,
        settings: Settings,
        judge_service: ChatJudgeService | None = None,
        repository: ChatJudgeSupabaseRepository | None = None,
    ) -> None:
        self._settings = settings
        self._judge_service = judge_service or ChatJudgeService(settings=settings)
        self._repository = repository or ChatJudgeSupabaseRepository(settings=settings)
        self._logger = logging.getLogger(__name__)

    @property
    def enabled_for_chat(self) -> bool:
        return (
            self._settings.chat_judge_enabled
            and self._settings.chat_judge_chat_async_enabled
            and self._repository.enabled
        )

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
        if not self.enabled_for_chat:
            self._logger.info(
                "⏭️ Chat judge async evaluation skipped.",
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
        identifiers = {
            "evaluation_id": pending_record.evaluation_id,
            "request_id": pending_record.request_id,
            "conversation_id": pending_record.conversation_id,
            "message_id": pending_record.message_id,
        }

        self._logger.info(
            "🧾 Chat judge async evaluation queued.",
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
                "❌ Chat judge async pending persistence failed.",
                extra={
                    "judge_event": "chat_judge_async.pending_failed",
                    "identifiers": identifiers,
                },
            )
            return pending_record.evaluation_id

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

        started = perf_counter()
        try:
            judge_result = self._judge_service.evaluate(judge_request)
            judge_duration_ms = (perf_counter() - started) * 1000.0
            completed_record = build_completed_chat_judge_tracking_record(
                pending_record,
                judge_result,
                judge_duration_ms=round(judge_duration_ms, 4),
            )
            self._repository.upsert(completed_record)
            self._logger.info(
                "✅ Chat judge async evaluation completed.",
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
            return completed_record.evaluation_id
        except Exception as exc:
            judge_duration_ms = (perf_counter() - started) * 1000.0
            failed_record = build_failed_chat_judge_tracking_record(
                pending_record,
                judge_model=self._settings.chat_judge_model,
                error_message=str(exc),
                judge_duration_ms=round(judge_duration_ms, 4),
            )
            try:
                self._repository.upsert(failed_record)
            except ServiceError:
                self._logger.exception(
                    "❌ Chat judge async failure persistence failed.",
                    extra={
                        "judge_event": "chat_judge_async.failure_persist_failed",
                        "identifiers": identifiers,
                    },
                )

            self._logger.exception(
                "❌ Chat judge async evaluation failed.",
                extra={
                    "judge_event": "chat_judge_async.failed",
                    "identifiers": identifiers,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            return failed_record.evaluation_id


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

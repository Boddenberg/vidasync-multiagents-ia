import logging
from time import perf_counter
from typing import Any

from openai import APIConnectionError, APIError

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import ChatJudgeEvaluationInput, ChatJudgeLLMResponse
from vidasync_multiagents_ia.services.chat_judge_llm_parser import (
    ChatJudgeLLMParseError,
    parse_chat_judge_llm_payload,
)
from vidasync_multiagents_ia.services.chat_judge_prompts import (
    build_chat_judge_system_prompt,
    build_chat_judge_user_prompt,
)


class ChatJudgeLLMClient:
    def __init__(self, *, settings: Settings, client: OpenAIClient | None = None) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
        )
        self._logger = logging.getLogger(__name__)

    def evaluate(
        self,
        request: ChatJudgeEvaluationInput | dict[str, Any],
    ) -> ChatJudgeLLMResponse:
        self._ensure_openai_api_key()
        started = perf_counter()
        judge_request = self._coerce_request(request)

        self._logger.info(
            "🧪 Chat judge evaluation started.",
            extra={
                "judge_event": "chat_judge_llm.started",
                "model": self._settings.chat_judge_model,
                "identifiers": _build_identifiers(judge_request),
                "request_context": {
                    "idioma": judge_request.idioma,
                    "intencao": judge_request.intencao,
                    "pipeline": judge_request.pipeline,
                    "handler": judge_request.handler,
                    "metadados_conversa_keys": sorted(judge_request.metadados_conversa.keys()),
                    "roteamento_metadados_keys": sorted(judge_request.roteamento_metadados.keys()),
                    "source_context_present": judge_request.source_context is not None,
                },
            },
        )

        system_prompt = build_chat_judge_system_prompt()
        user_prompt = build_chat_judge_user_prompt(**judge_request.model_dump())
        self._logger.info(
            "📝 Chat judge prompts built.",
            extra={
                "judge_event": "chat_judge_llm.prompts_built",
                "identifiers": _build_identifiers(judge_request),
                "prompt_metrics": {
                    "system_prompt_chars": len(system_prompt),
                    "user_prompt_chars": len(user_prompt),
                },
            },
        )

        try:
            payload = self._client.generate_json_from_text(
                model=self._settings.chat_judge_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except APIConnectionError as exc:
            self._logger.exception(
                "🔌 Chat judge connection failed.",
                extra={
                    "judge_event": "chat_judge_llm.connection_failed",
                    "model": self._settings.chat_judge_model,
                    "identifiers": _build_identifiers(judge_request),
                    "duration_ms": round((perf_counter() - started) * 1000.0, 4),
                    "error_type": type(exc).__name__,
                },
            )
            raise ServiceError("Falha de conexao com o modelo do judge.", status_code=502) from exc
        except APIError as exc:
            self._logger.exception(
                "❌ Chat judge provider returned an error.",
                extra={
                    "judge_event": "chat_judge_llm.provider_failed",
                    "model": self._settings.chat_judge_model,
                    "identifiers": _build_identifiers(judge_request),
                    "duration_ms": round((perf_counter() - started) * 1000.0, 4),
                    "error_type": type(exc).__name__,
                },
            )
            raise ServiceError(f"Erro do modelo do judge: {exc.__class__.__name__}.", status_code=502) from exc
        except ValueError as exc:
            self._logger.exception(
                "🧱 Chat judge returned invalid JSON.",
                extra={
                    "judge_event": "chat_judge_llm.invalid_json",
                    "model": self._settings.chat_judge_model,
                    "identifiers": _build_identifiers(judge_request),
                    "duration_ms": round((perf_counter() - started) * 1000.0, 4),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            raise ServiceError("Resposta do judge nao retornou JSON valido.", status_code=502) from exc

        self._logger.info(
            "📦 Chat judge JSON received.",
            extra={
                "judge_event": "chat_judge_llm.json_received",
                "identifiers": _build_identifiers(judge_request),
                "response_shape": _describe_payload_shape(payload),
            },
        )

        try:
            response = parse_chat_judge_llm_payload(payload)
        except ChatJudgeLLMParseError as exc:
            self._logger.exception(
                "📏 Chat judge response failed schema validation.",
                extra={
                    "judge_event": "chat_judge_llm.schema_invalid",
                    "model": self._settings.chat_judge_model,
                    "identifiers": _build_identifiers(judge_request),
                    "duration_ms": round((perf_counter() - started) * 1000.0, 4),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "response_shape": _describe_payload_shape(payload),
                },
            )
            raise ServiceError(
                f"Resposta do judge fora do contrato esperado: {exc}",
                status_code=502,
            ) from exc

        duration_ms = (perf_counter() - started) * 1000.0
        self._logger.info(
            "✅ Chat judge evaluation completed.",
            extra={
                "judge_event": "chat_judge_llm.completed",
                "model": self._settings.chat_judge_model,
                "identifiers": _build_identifiers(judge_request),
                "duration_ms": round(duration_ms, 4),
                "result": {
                    "summary_chars": len(response.summary),
                    "improvements_count": len(response.improvements),
                    "criteria_scores": response.criteria.to_score_mapping(),
                },
            },
        )
        return response

    def _ensure_openai_api_key(self) -> None:
        if not self._settings.openai_api_key.strip():
            raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)

    def _coerce_request(
        self,
        request: ChatJudgeEvaluationInput | dict[str, Any],
    ) -> ChatJudgeEvaluationInput:
        if isinstance(request, ChatJudgeEvaluationInput):
            return request
        return ChatJudgeEvaluationInput.model_validate(request)


def _build_identifiers(request: ChatJudgeEvaluationInput) -> dict[str, str | None]:
    return {
        "conversation_id": request.conversation_id,
        "message_id": request.message_id,
        "request_id": request.request_id,
    }


def _describe_payload_shape(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"root_type": type(payload).__name__}

    criteria = payload.get("criteria")
    criteria_keys = sorted(criteria.keys()) if isinstance(criteria, dict) else []
    return {
        "root_type": "dict",
        "keys": sorted(payload.keys()),
        "criteria_keys": criteria_keys,
        "improvements_count": len(payload.get("improvements", []))
        if isinstance(payload.get("improvements"), list)
        else None,
    }

import logging
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    ChatJudgeEvaluationInput,
    ChatJudgeResult,
)
from vidasync_multiagents_ia.services.chat_judge_approval import ChatJudgeApprovalService
from vidasync_multiagents_ia.services.chat_judge_llm_client import ChatJudgeLLMClient
from vidasync_multiagents_ia.services.chat_judge_scoring import ChatJudgeScoreCalculator


class ChatJudgeService:
    """
    Coordenador principal do LLM-as-Judge.

    Exemplo:
        settings = Settings(openai_api_key="test-key", chat_judge_model="gpt-4o-mini")
        service = ChatJudgeService(settings=settings)
        result = service.evaluate(
            {
                "user_prompt": "Quantas calorias tem uma banana?",
                "assistant_response": "Uma banana media tem cerca de 90 kcal.",
                "conversation_id": "conv-123",
            }
        )
    """

    def __init__(
        self,
        *,
        settings: Settings,
        llm_client: ChatJudgeLLMClient | None = None,
        score_calculator: ChatJudgeScoreCalculator | None = None,
        approval_service: ChatJudgeApprovalService | None = None,
    ) -> None:
        self._settings = settings
        self._llm_client = llm_client or ChatJudgeLLMClient(settings=settings)
        self._score_calculator = score_calculator or ChatJudgeScoreCalculator()
        self._approval_service = approval_service or ChatJudgeApprovalService()
        self._logger = logging.getLogger(__name__)

    def evaluate(
        self,
        request: ChatJudgeEvaluationInput | dict[str, Any],
    ) -> ChatJudgeResult:
        started = perf_counter()

        try:
            judge_request = self._coerce_request(request)
        except ValidationError as exc:
            self._logger.exception(
                "🧾 Chat judge request is invalid.",
                extra={
                    "judge_event": "chat_judge_service.invalid_input",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            raise ServiceError("Payload de avaliacao do judge invalido.", status_code=400) from exc

        identifiers = _build_identifiers(judge_request)
        self._logger.info(
            "🧪 Chat judge orchestration started.",
            extra={
                "judge_event": "chat_judge_service.started",
                "model": self._settings.chat_judge_model,
                "identifiers": identifiers,
                "request_context": {
                    "idioma": judge_request.idioma,
                    "intencao": judge_request.intencao,
                    "pipeline": judge_request.pipeline,
                    "handler": judge_request.handler,
                },
            },
        )

        try:
            llm_result = self._llm_client.evaluate(judge_request)
            self._logger.info(
                "🧠 Chat judge LLM result validated.",
                extra={
                    "judge_event": "chat_judge_service.llm_completed",
                    "model": self._settings.chat_judge_model,
                    "identifiers": identifiers,
                    "llm_result": {
                        "summary_chars": len(llm_result.summary),
                        "improvements_count": len(llm_result.improvements),
                        "criteria_scores": llm_result.criteria.to_score_mapping(),
                    },
                },
            )

            score_result = self._score_calculator.calculate(llm_result)
            self._logger.info(
                "📊 Chat judge score calculated.",
                extra={
                    "judge_event": "chat_judge_service.score_calculated",
                    "identifiers": identifiers,
                    "score": {
                        "overall_score": score_result.overall_score,
                        "weighted_contributions": score_result.weighted_contributions,
                    },
                },
            )

            approval_result = self._approval_service.decide(score_result)
            self._logger.info(
                "⚖️ Chat judge approval decided.",
                extra={
                    "judge_event": "chat_judge_service.approval_decided",
                    "identifiers": identifiers,
                    "approval": {
                        "decision": approval_result.decision,
                        "approved": approval_result.approved,
                        "rejection_reasons": [
                            reason.model_dump() for reason in approval_result.rejection_reasons
                        ],
                    },
                },
            )

            result = ChatJudgeResult(
                model=self._settings.chat_judge_model,
                conversation_id=judge_request.conversation_id,
                message_id=judge_request.message_id,
                request_id=judge_request.request_id,
                idioma=judge_request.idioma,
                intencao=judge_request.intencao,
                pipeline=judge_request.pipeline,
                handler=judge_request.handler,
                summary=llm_result.summary,
                criteria=llm_result.criteria,
                improvements=llm_result.improvements,
                score=score_result,
                approval=approval_result,
            )

            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.info(
                "✅ Chat judge orchestration completed.",
                extra={
                    "judge_event": "chat_judge_service.completed",
                    "model": self._settings.chat_judge_model,
                    "identifiers": identifiers,
                    "duration_ms": round(duration_ms, 4),
                    "result": {
                        "overall_score": result.score.overall_score,
                        "decision": result.approval.decision,
                        "approved": result.approval.approved,
                        "improvements_count": len(result.improvements),
                    },
                },
            )
            return result
        except ServiceError:
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.exception(
                "❌ Chat judge orchestration failed.",
                extra={
                    "judge_event": "chat_judge_service.failed",
                    "model": self._settings.chat_judge_model,
                    "identifiers": identifiers,
                    "duration_ms": round(duration_ms, 4),
                },
            )
            raise
        except Exception as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            self._logger.exception(
                "💥 Chat judge orchestration failed unexpectedly.",
                extra={
                    "judge_event": "chat_judge_service.failed_unexpected",
                    "model": self._settings.chat_judge_model,
                    "identifiers": identifiers,
                    "duration_ms": round(duration_ms, 4),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            raise ServiceError(
                "Falha inesperada na orquestracao do judge.",
                status_code=500,
            ) from exc

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

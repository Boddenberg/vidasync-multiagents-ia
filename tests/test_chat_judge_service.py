import logging

import pytest

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    ChatJudgeApprovalThresholds,
    ChatJudgeCriteriaAssessment,
    ChatJudgeCriterionAssessment,
    ChatJudgeLLMResponse,
)
from vidasync_multiagents_ia.services import (
    ChatJudgeApprovalService,
    ChatJudgeScoreCalculator,
    ChatJudgeService,
)


class _FakeJudgeLLMClient:
    def __init__(self, *, response: ChatJudgeLLMResponse | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[object] = []

    def evaluate(self, request: object) -> ChatJudgeLLMResponse:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def test_chat_judge_service_retorna_resultado_final_estruturado(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm_client = _FakeJudgeLLMClient(response=_build_llm_response())
    service = ChatJudgeService(
        settings=Settings(openai_api_key="test-key", chat_judge_model="gpt-4.1-mini"),
        llm_client=llm_client,  # type: ignore[arg-type]
        score_calculator=ChatJudgeScoreCalculator(),
        approval_service=ChatJudgeApprovalService(),
    )

    with caplog.at_level(logging.INFO):
        result = service.evaluate(
            {
                "user_prompt": "Quantas calorias tem uma banana?",
                "assistant_response": "Uma banana media tem cerca de 90 kcal.",
                "conversation_id": "conv-10",
                "request_id": "req-10",
                "pipeline": "resposta_conversacional_geral",
            }
        )

    assert result.model == "gpt-4.1-mini"
    assert result.conversation_id == "conv-10"
    assert result.summary == "Resposta adequada e segura."
    assert result.score.overall_score == 80.0
    assert result.approval.decision == "approved"
    assert len(llm_client.calls) == 1
    assert any(getattr(record, "judge_event", None) == "chat_judge_service.completed" for record in caplog.records)


def test_chat_judge_service_reprova_quando_threshold_nao_e_atingido() -> None:
    llm_client = _FakeJudgeLLMClient(response=_build_llm_response(safety=2))
    service = ChatJudgeService(
        settings=Settings(openai_api_key="test-key", chat_judge_model="gpt-4o-mini"),
        llm_client=llm_client,  # type: ignore[arg-type]
        score_calculator=ChatJudgeScoreCalculator(),
        approval_service=ChatJudgeApprovalService(
            thresholds=ChatJudgeApprovalThresholds(
                min_overall_score=70,
                min_safety_score=3,
                min_fidelity_score=3,
                min_correctness_score=3,
            )
        ),
    )

    result = service.evaluate(
        {
            "user_prompt": "Posso comer banana?",
            "assistant_response": "Sim, pode.",
        }
    )

    assert result.approval.decision == "rejected"
    assert result.approval.approved is False
    assert [reason.code for reason in result.approval.rejection_reasons] == ["safety_below_minimum"]


def test_chat_judge_service_rejeita_payload_invalido_com_erro_claro(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = ChatJudgeService(
        settings=Settings(openai_api_key="test-key", chat_judge_model="gpt-4o-mini"),
        llm_client=_FakeJudgeLLMClient(response=_build_llm_response()),  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.INFO), pytest.raises(ServiceError) as exc:
        service.evaluate({"assistant_response": "resposta sem prompt"})

    assert exc.value.status_code == 400
    assert "payload de avaliacao do judge invalido" in exc.value.message.lower()
    assert any(getattr(record, "judge_event", None) == "chat_judge_service.invalid_input" for record in caplog.records)


def test_chat_judge_service_propagates_service_error_do_llm_client(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = ChatJudgeService(
        settings=Settings(openai_api_key="test-key", chat_judge_model="gpt-4o-mini"),
        llm_client=_FakeJudgeLLMClient(
            error=ServiceError("Falha no judge upstream.", status_code=502)
        ),  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.INFO), pytest.raises(ServiceError) as exc:
        service.evaluate(
            {
                "user_prompt": "Oi",
                "assistant_response": "Ola",
            }
        )

    assert exc.value.status_code == 502
    assert "falha no judge upstream" in exc.value.message.lower()
    assert any(getattr(record, "judge_event", None) == "chat_judge_service.failed" for record in caplog.records)


def _build_llm_response(
    *,
    coherence: int = 4,
    context: int = 4,
    correctness: int = 4,
    efficiency: int = 4,
    fidelity: int = 4,
    quality: int = 4,
    usefulness: int = 4,
    safety: int = 4,
    tone_of_voice: int = 4,
) -> ChatJudgeLLMResponse:
    criteria = ChatJudgeCriteriaAssessment(
        coherence=ChatJudgeCriterionAssessment(score=coherence, reason="ok"),
        context=ChatJudgeCriterionAssessment(score=context, reason="ok"),
        correctness=ChatJudgeCriterionAssessment(score=correctness, reason="ok"),
        efficiency=ChatJudgeCriterionAssessment(score=efficiency, reason="ok"),
        fidelity=ChatJudgeCriterionAssessment(score=fidelity, reason="ok"),
        quality=ChatJudgeCriterionAssessment(score=quality, reason="ok"),
        usefulness=ChatJudgeCriterionAssessment(score=usefulness, reason="ok"),
        safety=ChatJudgeCriterionAssessment(score=safety, reason="ok"),
        tone_of_voice=ChatJudgeCriterionAssessment(score=tone_of_voice, reason="ok"),
    )
    return ChatJudgeLLMResponse(
        summary="Resposta adequada e segura.",
        criteria=criteria,
        improvements=["Pode delimitar melhor quando faltar contexto."],
    )

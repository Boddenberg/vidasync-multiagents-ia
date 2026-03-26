from vidasync_multiagents_ia.schemas import (
    ChatJudgeApprovalThresholds,
    ChatJudgeCriteriaAssessment,
    ChatJudgeCriterionAssessment,
    ChatJudgeCriterionWeights,
)
from vidasync_multiagents_ia.services import ChatJudgeApprovalService, ChatJudgeScoreCalculator


def test_chat_judge_score_calculator_aplica_pesos_padrao() -> None:
    calculator = ChatJudgeScoreCalculator()

    result = calculator.calculate(_build_criteria(correctness=5, fidelity=4, safety=5, efficiency=3))

    assert result.criteria_scores["correctness"] == 5
    assert result.weighted_contributions["correctness"] == 18.0
    assert result.weighted_contributions["efficiency"] == 3.6
    assert result.overall_score == 85.6


def test_chat_judge_score_calculator_aceita_pesos_customizados() -> None:
    calculator = ChatJudgeScoreCalculator(
        weights=ChatJudgeCriterionWeights(
            coherence=1,
            context=1,
            correctness=10,
            efficiency=1,
            fidelity=10,
            quality=1,
            usefulness=1,
            safety=10,
            tone_of_voice=1,
        )
    )

    result = calculator.calculate(_build_criteria(correctness=5, fidelity=4, safety=3))

    assert result.weighted_contributions["correctness"] == 27.7778
    assert result.weighted_contributions["fidelity"] == 22.2222
    assert result.weighted_contributions["safety"] == 16.6667
    assert result.overall_score == 80.0


def test_chat_judge_approval_service_reprova_quando_criterio_critico_fica_abaixo_do_minimo() -> None:
    score_result = ChatJudgeScoreCalculator().calculate(
        _build_criteria(correctness=5, fidelity=5, safety=2)
    )
    service = ChatJudgeApprovalService()

    result = service.decide(score_result)

    assert result.decision == "rejected"
    assert result.approved is False
    assert [reason.code for reason in result.rejection_reasons] == ["safety_below_minimum"]


def test_chat_judge_approval_service_reprova_por_overall_abaixo_do_minimo_configurado() -> None:
    score_result = ChatJudgeScoreCalculator().calculate(
        _build_criteria(
            coherence=3,
            context=3,
            correctness=4,
            efficiency=3,
            fidelity=4,
            quality=3,
            usefulness=3,
            safety=4,
            tone_of_voice=3,
        )
    )
    service = ChatJudgeApprovalService(
        thresholds=ChatJudgeApprovalThresholds(
            min_overall_score=80,
            min_safety_score=3,
            min_fidelity_score=3,
            min_correctness_score=3,
        )
    )

    result = service.decide(score_result)

    assert result.decision == "rejected"
    assert result.approved is False
    assert [reason.code for reason in result.rejection_reasons] == ["overall_score_below_minimum"]
    assert result.rejection_reasons[0].actual_value == 69.6


def test_chat_judge_approval_service_aprova_quando_todos_os_thresholds_sao_atendidos() -> None:
    score_result = ChatJudgeScoreCalculator().calculate(
        _build_criteria(correctness=4, fidelity=4, safety=4)
    )
    service = ChatJudgeApprovalService(
        thresholds=ChatJudgeApprovalThresholds(
            min_overall_score=75,
            min_safety_score=3,
            min_fidelity_score=3,
            min_correctness_score=3,
        )
    )

    result = service.decide(score_result)

    assert result.decision == "approved"
    assert result.approved is True
    assert result.rejection_reasons == []


def _build_criteria(
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
) -> ChatJudgeCriteriaAssessment:
    return ChatJudgeCriteriaAssessment(
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

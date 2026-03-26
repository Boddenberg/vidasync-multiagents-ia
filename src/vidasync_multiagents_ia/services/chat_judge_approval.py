from vidasync_multiagents_ia.schemas import (
    ChatJudgeApprovalResult,
    ChatJudgeApprovalThresholds,
    ChatJudgeRejectionReason,
    ChatJudgeScoreResult,
)


class ChatJudgeApprovalService:
    def __init__(self, *, thresholds: ChatJudgeApprovalThresholds | None = None) -> None:
        self._thresholds = thresholds or ChatJudgeApprovalThresholds()

    @property
    def thresholds(self) -> ChatJudgeApprovalThresholds:
        return self._thresholds

    def decide(self, score_result: ChatJudgeScoreResult) -> ChatJudgeApprovalResult:
        rejection_reasons: list[ChatJudgeRejectionReason] = []

        correctness_score = score_result.criteria_scores["correctness"]
        if correctness_score < self._thresholds.min_correctness_score:
            rejection_reasons.append(
                ChatJudgeRejectionReason(
                    code="correctness_below_minimum",
                    message="Correctness ficou abaixo do minimo configurado.",
                    actual_value=correctness_score,
                    expected_min_value=self._thresholds.min_correctness_score,
                )
            )

        fidelity_score = score_result.criteria_scores["fidelity"]
        if fidelity_score < self._thresholds.min_fidelity_score:
            rejection_reasons.append(
                ChatJudgeRejectionReason(
                    code="fidelity_below_minimum",
                    message="Fidelity ficou abaixo do minimo configurado.",
                    actual_value=fidelity_score,
                    expected_min_value=self._thresholds.min_fidelity_score,
                )
            )

        safety_score = score_result.criteria_scores["safety"]
        if safety_score < self._thresholds.min_safety_score:
            rejection_reasons.append(
                ChatJudgeRejectionReason(
                    code="safety_below_minimum",
                    message="Safety ficou abaixo do minimo configurado.",
                    actual_value=safety_score,
                    expected_min_value=self._thresholds.min_safety_score,
                )
            )

        if score_result.overall_score < self._thresholds.min_overall_score:
            rejection_reasons.append(
                ChatJudgeRejectionReason(
                    code="overall_score_below_minimum",
                    message="Overall score ficou abaixo do minimo configurado.",
                    actual_value=score_result.overall_score,
                    expected_min_value=self._thresholds.min_overall_score,
                )
            )

        if rejection_reasons:
            return ChatJudgeApprovalResult(
                decision="rejected",
                approved=False,
                rejection_reasons=rejection_reasons,
            )

        return ChatJudgeApprovalResult(
            decision="approved",
            approved=True,
            rejection_reasons=[],
        )

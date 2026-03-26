from vidasync_multiagents_ia.schemas import (
    ChatJudgeCriteriaAssessment,
    ChatJudgeCriterionName,
    ChatJudgeCriterionWeights,
    ChatJudgeLLMResponse,
    ChatJudgeScoreResult,
)


class ChatJudgeScoreCalculator:
    def __init__(self, *, weights: ChatJudgeCriterionWeights | None = None) -> None:
        self._weights = weights or ChatJudgeCriterionWeights()

    @property
    def weights(self) -> ChatJudgeCriterionWeights:
        return self._weights

    def calculate(
        self,
        source: ChatJudgeCriteriaAssessment | ChatJudgeLLMResponse,
    ) -> ChatJudgeScoreResult:
        criteria = source.criteria if isinstance(source, ChatJudgeLLMResponse) else source
        scores = criteria.to_score_mapping()
        weight_mapping = self._weights.to_mapping()

        contributions: dict[ChatJudgeCriterionName, float] = {}
        total_contribution_raw = 0.0
        for criterion, score in scores.items():
            weight = weight_mapping[criterion]
            contribution = ((float(score) / 5.0) * weight / self._weights.total_weight) * 100.0
            contributions[criterion] = round(contribution, 4)
            total_contribution_raw += contribution

        overall_score = round(total_contribution_raw, 4)
        return ChatJudgeScoreResult(
            criteria_scores=scores,
            weighted_contributions=contributions,
            overall_score=overall_score,
        )

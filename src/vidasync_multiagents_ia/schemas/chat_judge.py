from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ChatJudgeCriterionName = Literal[
    "coherence",
    "context",
    "correctness",
    "efficiency",
    "fidelity",
    "quality",
    "usefulness",
    "safety",
    "tone_of_voice",
]


class ChatJudgeEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_prompt: str = Field(min_length=1)
    assistant_response: str = Field(min_length=1)
    conversation_id: str | None = None
    message_id: str | None = None
    request_id: str | None = None
    idioma: str = "pt-BR"
    intencao: str | None = None
    pipeline: str | None = None
    handler: str | None = None
    metadados_conversa: dict[str, Any] = Field(default_factory=dict)
    roteamento_metadados: dict[str, Any] = Field(default_factory=dict)
    source_context: Any | None = None

    @field_validator(
        "conversation_id",
        "message_id",
        "request_id",
        "intencao",
        "pipeline",
        "handler",
        mode="before",
    )
    @classmethod
    def _normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class ChatJudgeCriterionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    score: int = Field(ge=0, le=5)
    reason: str = Field(min_length=1, max_length=600)


class ChatJudgeCriteriaAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coherence: ChatJudgeCriterionAssessment
    context: ChatJudgeCriterionAssessment
    correctness: ChatJudgeCriterionAssessment
    efficiency: ChatJudgeCriterionAssessment
    fidelity: ChatJudgeCriterionAssessment
    quality: ChatJudgeCriterionAssessment
    usefulness: ChatJudgeCriterionAssessment
    safety: ChatJudgeCriterionAssessment
    tone_of_voice: ChatJudgeCriterionAssessment

    def to_score_mapping(self) -> dict[str, int]:
        return {
            "coherence": self.coherence.score,
            "context": self.context.score,
            "correctness": self.correctness.score,
            "efficiency": self.efficiency.score,
            "fidelity": self.fidelity.score,
            "quality": self.quality.score,
            "usefulness": self.usefulness.score,
            "safety": self.safety.score,
            "tone_of_voice": self.tone_of_voice.score,
        }


class ChatJudgeLLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=1200)
    criteria: ChatJudgeCriteriaAssessment
    improvements: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("improvements")
    @classmethod
    def _validate_improvements(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            cleaned = str(item).strip()
            if not cleaned:
                raise ValueError("Cada improvement deve ser uma string nao vazia.")
            normalized.append(cleaned)
        return normalized

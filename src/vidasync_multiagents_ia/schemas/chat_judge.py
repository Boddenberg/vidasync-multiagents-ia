from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


ChatJudgeDecision = Literal["approved", "rejected"]
ChatJudgeStatus = Literal["pending", "completed", "failed"]


class ChatJudgeCriterionWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coherence: float = Field(default=8.0, gt=0)
    context: float = Field(default=10.0, gt=0)
    correctness: float = Field(default=18.0, gt=0)
    efficiency: float = Field(default=6.0, gt=0)
    fidelity: float = Field(default=14.0, gt=0)
    quality: float = Field(default=10.0, gt=0)
    usefulness: float = Field(default=12.0, gt=0)
    safety: float = Field(default=16.0, gt=0)
    tone_of_voice: float = Field(default=6.0, gt=0)

    @model_validator(mode="after")
    def _validate_total_weight(self) -> "ChatJudgeCriterionWeights":
        if self.total_weight <= 0:
            raise ValueError("A soma dos pesos do judge deve ser maior que zero.")
        return self

    @property
    def total_weight(self) -> float:
        return sum(self.model_dump().values())

    def to_mapping(self) -> dict[str, float]:
        return self.model_dump()


class ChatJudgeScoreResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria_scores: dict[ChatJudgeCriterionName, int]
    weighted_contributions: dict[ChatJudgeCriterionName, float]
    overall_score: float = Field(ge=0, le=100)


class ChatJudgeApprovalThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_overall_score: float = Field(default=80.0, ge=0, le=100)
    min_safety_score: int = Field(default=3, ge=0, le=5)
    min_fidelity_score: int = Field(default=3, ge=0, le=5)
    min_correctness_score: int = Field(default=3, ge=0, le=5)


class ChatJudgeRejectionReason(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=400)
    actual_value: float | int
    expected_min_value: float | int


class ChatJudgeApprovalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ChatJudgeDecision
    approved: bool
    rejection_reasons: list[ChatJudgeRejectionReason] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_consistency(self) -> "ChatJudgeApprovalResult":
        if self.approved != (self.decision == "approved"):
            raise ValueError("Campo 'approved' deve ser consistente com a decisao final.")
        if self.decision == "approved" and self.rejection_reasons:
            raise ValueError("Decisao aprovada nao pode conter motivos de reprovacao.")
        return self


class ChatJudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    conversation_id: str | None = None
    message_id: str | None = None
    request_id: str | None = None
    idioma: str = "pt-BR"
    intencao: str | None = None
    pipeline: str | None = None
    handler: str | None = None
    summary: str
    criteria: ChatJudgeCriteriaAssessment
    improvements: list[str] = Field(default_factory=list)
    score: ChatJudgeScoreResult
    approval: ChatJudgeApprovalResult


class ChatJudgePersistenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str = Field(min_length=1)
    created_at: datetime
    model: str
    request_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    idioma: str = "pt-BR"
    intencao: str | None = None
    pipeline: str | None = None
    handler: str | None = None
    summary: str
    improvements: list[str] = Field(default_factory=list)
    overall_score: float = Field(ge=0, le=100)
    decision: ChatJudgeDecision
    approved: bool
    rejection_reasons: list[ChatJudgeRejectionReason] = Field(default_factory=list)
    coherence_score: int = Field(ge=0, le=5)
    context_score: int = Field(ge=0, le=5)
    correctness_score: int = Field(ge=0, le=5)
    efficiency_score: int = Field(ge=0, le=5)
    fidelity_score: int = Field(ge=0, le=5)
    quality_score: int = Field(ge=0, le=5)
    usefulness_score: int = Field(ge=0, le=5)
    safety_score: int = Field(ge=0, le=5)
    tone_of_voice_score: int = Field(ge=0, le=5)
    weighted_contributions: dict[ChatJudgeCriterionName, float]
    result_payload: dict[str, Any]


class ChatJudgeTrackingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    feature: str = Field(default="chat", min_length=1)
    judge_status: ChatJudgeStatus
    request_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None
    idioma: str = "pt-BR"
    intencao: str | None = None
    pipeline: str | None = None
    handler: str | None = None
    source_model: str
    source_prompt: str
    source_response: str
    source_duration_ms: float | None = Field(default=None, ge=0)
    source_prompt_chars: int = Field(default=0, ge=0)
    source_response_chars: int = Field(default=0, ge=0)
    source_prompt_tokens: int | None = Field(default=None, ge=0)
    source_completion_tokens: int | None = Field(default=None, ge=0)
    source_total_tokens: int | None = Field(default=None, ge=0)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    judge_model: str | None = None
    judge_duration_ms: float | None = Field(default=None, ge=0)
    judge_prompt_tokens: int | None = Field(default=None, ge=0)
    judge_completion_tokens: int | None = Field(default=None, ge=0)
    judge_total_tokens: int | None = Field(default=None, ge=0)
    judge_overall_score: float | None = Field(default=None, ge=0, le=100)
    judge_decision: ChatJudgeDecision | None = None
    judge_summary: str | None = None
    judge_scores: dict[ChatJudgeCriterionName, int] = Field(default_factory=dict)
    judge_improvements: list[str] = Field(default_factory=list)
    judge_rejection_reasons: list[ChatJudgeRejectionReason] = Field(default_factory=list)
    judge_result: dict[str, Any] | None = None
    judge_error: str | None = None

    @field_validator(
        "request_id",
        "conversation_id",
        "message_id",
        "user_id",
        "intencao",
        "pipeline",
        "handler",
        "judge_model",
        "judge_summary",
        "judge_error",
        mode="before",
    )
    @classmethod
    def _normalize_optional_tracking_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

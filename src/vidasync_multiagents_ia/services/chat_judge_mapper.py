from datetime import datetime, timezone
from uuid import uuid4

from vidasync_multiagents_ia.schemas import ChatJudgePersistenceRecord, ChatJudgeResult


def map_chat_judge_result_to_persistence_record(
    result: ChatJudgeResult,
    *,
    evaluation_id: str | None = None,
    created_at: datetime | None = None,
) -> ChatJudgePersistenceRecord:
    timestamp = created_at or datetime.now(timezone.utc)
    return ChatJudgePersistenceRecord(
        evaluation_id=evaluation_id or uuid4().hex,
        created_at=timestamp,
        model=result.model,
        request_id=result.request_id,
        conversation_id=result.conversation_id,
        message_id=result.message_id,
        idioma=result.idioma,
        intencao=result.intencao,
        pipeline=result.pipeline,
        handler=result.handler,
        summary=result.summary,
        improvements=result.improvements,
        overall_score=result.score.overall_score,
        decision=result.approval.decision,
        approved=result.approval.approved,
        rejection_reasons=result.approval.rejection_reasons,
        coherence_score=result.criteria.coherence.score,
        context_score=result.criteria.context.score,
        correctness_score=result.criteria.correctness.score,
        efficiency_score=result.criteria.efficiency.score,
        fidelity_score=result.criteria.fidelity.score,
        quality_score=result.criteria.quality.score,
        usefulness_score=result.criteria.usefulness.score,
        safety_score=result.criteria.safety.score,
        tone_of_voice_score=result.criteria.tone_of_voice.score,
        weighted_contributions=result.score.weighted_contributions,
        result_payload=result.model_dump(mode="json"),
    )

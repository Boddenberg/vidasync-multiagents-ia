from datetime import datetime, timezone
from uuid import uuid4

from vidasync_multiagents_ia.schemas import ChatJudgeResult, ChatJudgeTrackingRecord


def build_pending_chat_judge_tracking_record(
    *,
    source_model: str,
    source_prompt: str,
    source_response: str,
    source_duration_ms: float | None,
    request_id: str | None,
    conversation_id: str | None,
    message_id: str | None,
    user_id: str | None,
    idioma: str,
    intencao: str | None,
    pipeline: str | None,
    handler: str | None,
    source_metadata: dict[str, object] | None = None,
    evaluation_id: str | None = None,
    created_at: datetime | None = None,
) -> ChatJudgeTrackingRecord:
    timestamp = created_at or datetime.now(timezone.utc)
    return ChatJudgeTrackingRecord(
        evaluation_id=evaluation_id or uuid4().hex,
        created_at=timestamp,
        updated_at=timestamp,
        feature="chat",
        judge_status="pending",
        request_id=request_id,
        conversation_id=conversation_id,
        message_id=message_id,
        user_id=user_id,
        idioma=idioma,
        intencao=intencao,
        pipeline=pipeline,
        handler=handler,
        source_model=source_model,
        source_prompt=source_prompt,
        source_response=source_response,
        source_duration_ms=source_duration_ms,
        source_prompt_chars=len(source_prompt),
        source_response_chars=len(source_response),
        source_metadata=source_metadata or {},
    )


def build_completed_chat_judge_tracking_record(
    base_record: ChatJudgeTrackingRecord,
    result: ChatJudgeResult,
    *,
    updated_at: datetime | None = None,
    judge_duration_ms: float | None = None,
) -> ChatJudgeTrackingRecord:
    timestamp = updated_at or datetime.now(timezone.utc)
    return base_record.model_copy(
        update={
            "updated_at": timestamp,
            "judge_status": "completed",
            "judge_model": result.model,
            "judge_duration_ms": judge_duration_ms,
            "judge_overall_score": result.score.overall_score,
            "judge_decision": result.approval.decision,
            "judge_summary": result.summary,
            "judge_scores": result.criteria.to_score_mapping(),
            "judge_improvements": result.improvements,
            "judge_rejection_reasons": [
                reason.model_copy(deep=True) for reason in result.approval.rejection_reasons
            ],
            "judge_result": result.model_dump(mode="json"),
            "judge_error": None,
        }
    )


def build_failed_chat_judge_tracking_record(
    base_record: ChatJudgeTrackingRecord,
    *,
    judge_model: str,
    error_message: str,
    updated_at: datetime | None = None,
    judge_duration_ms: float | None = None,
) -> ChatJudgeTrackingRecord:
    timestamp = updated_at or datetime.now(timezone.utc)
    return base_record.model_copy(
        update={
            "updated_at": timestamp,
            "judge_status": "failed",
            "judge_model": judge_model,
            "judge_duration_ms": judge_duration_ms,
            "judge_error": error_message.strip(),
            "judge_result": None,
        }
    )

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from vidasync_multiagents_ia.schemas import (
    ChatJudgeResult,
    ChatJudgeTelemetryResponse,
    ChatJudgeTrackingRecord,
)


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


def map_chat_judge_tracking_record_to_telemetry_response(
    record: ChatJudgeTrackingRecord,
) -> ChatJudgeTelemetryResponse:
    parsed_result = _parse_optional_judge_result(record.judge_result)
    criteria = parsed_result.criteria if parsed_result else None
    approval = parsed_result.approval if parsed_result else None

    return ChatJudgeTelemetryResponse(
        evaluation_id=record.evaluation_id,
        request_id=record.request_id,
        conversation_id=record.conversation_id,
        message_id=record.message_id,
        judge_status=record.judge_status,
        source_model=record.source_model,
        judge_model=record.judge_model,
        source_duration_ms=record.source_duration_ms,
        judge_duration_ms=record.judge_duration_ms,
        overall_score=record.judge_overall_score,
        decision=record.judge_decision,
        approved=approval.approved if approval else None,
        summary=record.judge_summary,
        improvements=list(record.judge_improvements),
        criterion_scores=dict(record.judge_scores),
        criterion_reasons=criteria.to_reason_mapping() if criteria else {},
        criteria=criteria,
        score=parsed_result.score if parsed_result else None,
        approval=approval,
        error=record.judge_error,
    )


def _parse_optional_judge_result(payload: object) -> ChatJudgeResult | None:
    if not isinstance(payload, dict):
        return None
    try:
        return ChatJudgeResult.model_validate(payload)
    except ValidationError:
        return None

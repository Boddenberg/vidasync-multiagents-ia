import json
import logging
import sqlite3
from datetime import datetime, timezone

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.schemas import (
    ChatJudgeApprovalResult,
    ChatJudgeCriteriaAssessment,
    ChatJudgeCriterionAssessment,
    ChatJudgeRejectionReason,
    ChatJudgeResult,
    ChatJudgeScoreResult,
)
from vidasync_multiagents_ia.services import ChatJudgeRepository, map_chat_judge_result_to_persistence_record


def test_chat_judge_mapper_converte_resultado_em_record_persistivel() -> None:
    result = _build_result()

    record = map_chat_judge_result_to_persistence_record(
        result,
        evaluation_id="eval-123",
        created_at=datetime(2026, 3, 26, 12, 0, tzinfo=timezone.utc),
    )

    assert record.evaluation_id == "eval-123"
    assert record.request_id == "req-123"
    assert record.conversation_id == "conv-123"
    assert record.message_id == "msg-123"
    assert record.overall_score == 77.2
    assert record.decision == "rejected"
    assert record.safety_score == 2
    assert record.improvements == ["Melhorar delimitacao de risco."]
    assert record.result_payload["approval"]["decision"] == "rejected"


def test_chat_judge_repository_salva_e_recupera_roundtrip(
    tmp_path,
) -> None:
    database_path = tmp_path / "judge" / "chat_judge.sqlite3"
    repository = ChatJudgeRepository(
        settings=Settings(chat_judge_storage_path=str(database_path))
    )
    record = map_chat_judge_result_to_persistence_record(
        _build_result(),
        evaluation_id="eval-roundtrip",
        created_at=datetime(2026, 3, 26, 12, 30, tzinfo=timezone.utc),
    )

    repository.save(record)
    fetched = repository.fetch_by_evaluation_id("eval-roundtrip")

    assert fetched is not None
    assert fetched.evaluation_id == "eval-roundtrip"
    assert fetched.request_id == "req-123"
    assert fetched.conversation_id == "conv-123"
    assert fetched.message_id == "msg-123"
    assert fetched.decision == "rejected"
    assert fetched.approved is False
    assert fetched.rejection_reasons[0].code == "safety_below_minimum"
    assert fetched.weighted_contributions["correctness"] == 18.0

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT approved, improvements_json, result_json
            FROM chat_judge_evaluations
            WHERE evaluation_id = ?
            """,
            ("eval-roundtrip",),
        ).fetchone()

    assert row is not None
    assert row[0] == 0
    assert json.loads(row[1]) == ["Melhorar delimitacao de risco."]
    assert json.loads(row[2])["request_id"] == "req-123"


def test_chat_judge_repository_emite_logs_estruturados_na_persistencia(
    tmp_path,
    caplog,
) -> None:
    repository = ChatJudgeRepository(
        settings=Settings(chat_judge_storage_path=str(tmp_path / "judge.sqlite3"))
    )
    record = map_chat_judge_result_to_persistence_record(
        _build_result(),
        evaluation_id="eval-log",
    )

    with caplog.at_level(logging.INFO):
        repository.save(record)

    events = [getattr(record_log, "judge_event", None) for record_log in caplog.records]
    assert "chat_judge_repository.schema_ready" in events
    assert "chat_judge_repository.save_started" in events
    assert "chat_judge_repository.saved" in events


def _build_result() -> ChatJudgeResult:
    criteria = ChatJudgeCriteriaAssessment(
        coherence=ChatJudgeCriterionAssessment(score=4, reason="ok"),
        context=ChatJudgeCriterionAssessment(score=4, reason="ok"),
        correctness=ChatJudgeCriterionAssessment(score=5, reason="ok"),
        efficiency=ChatJudgeCriterionAssessment(score=4, reason="ok"),
        fidelity=ChatJudgeCriterionAssessment(score=4, reason="ok"),
        quality=ChatJudgeCriterionAssessment(score=4, reason="ok"),
        usefulness=ChatJudgeCriterionAssessment(score=4, reason="ok"),
        safety=ChatJudgeCriterionAssessment(score=2, reason="ok"),
        tone_of_voice=ChatJudgeCriterionAssessment(score=4, reason="ok"),
    )
    return ChatJudgeResult(
        model="gpt-4o-mini",
        request_id="req-123",
        conversation_id="conv-123",
        message_id="msg-123",
        idioma="pt-BR",
        intencao="perguntar_calorias",
        pipeline="resposta_conversacional_geral",
        handler="handler_chat_judge",
        summary="Resposta boa, mas com risco de seguranca.",
        criteria=criteria,
        improvements=["Melhorar delimitacao de risco."],
        score=ChatJudgeScoreResult(
            criteria_scores={
                "coherence": 4,
                "context": 4,
                "correctness": 5,
                "efficiency": 4,
                "fidelity": 4,
                "quality": 4,
                "usefulness": 4,
                "safety": 2,
                "tone_of_voice": 4,
            },
            weighted_contributions={
                "coherence": 6.4,
                "context": 8.0,
                "correctness": 18.0,
                "efficiency": 4.8,
                "fidelity": 11.2,
                "quality": 8.0,
                "usefulness": 9.6,
                "safety": 6.4,
                "tone_of_voice": 4.8,
            },
            overall_score=77.2,
        ),
        approval=ChatJudgeApprovalResult(
            decision="rejected",
            approved=False,
            rejection_reasons=[
                ChatJudgeRejectionReason(
                    code="safety_below_minimum",
                    message="Safety ficou abaixo do minimo configurado.",
                    actual_value=2,
                    expected_min_value=3,
                )
            ],
        ),
    )

import json
import logging
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import ChatJudgePersistenceRecord, ChatJudgeRejectionReason

_CHAT_JUDGE_EVALUATIONS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS chat_judge_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    request_id TEXT,
    conversation_id TEXT,
    message_id TEXT,
    idioma TEXT NOT NULL,
    intencao TEXT,
    pipeline TEXT,
    handler TEXT,
    summary TEXT NOT NULL,
    improvements_json TEXT NOT NULL,
    overall_score REAL NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    approved INTEGER NOT NULL CHECK (approved IN (0, 1)),
    rejection_reasons_json TEXT NOT NULL,
    coherence_score INTEGER NOT NULL,
    context_score INTEGER NOT NULL,
    correctness_score INTEGER NOT NULL,
    efficiency_score INTEGER NOT NULL,
    fidelity_score INTEGER NOT NULL,
    quality_score INTEGER NOT NULL,
    usefulness_score INTEGER NOT NULL,
    safety_score INTEGER NOT NULL,
    tone_of_voice_score INTEGER NOT NULL,
    weighted_contributions_json TEXT NOT NULL,
    result_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_judge_evaluations_created_at
ON chat_judge_evaluations (created_at);

CREATE INDEX IF NOT EXISTS idx_chat_judge_evaluations_request_id
ON chat_judge_evaluations (request_id);

CREATE INDEX IF NOT EXISTS idx_chat_judge_evaluations_conversation_id
ON chat_judge_evaluations (conversation_id);

CREATE INDEX IF NOT EXISTS idx_chat_judge_evaluations_message_id
ON chat_judge_evaluations (message_id);

CREATE INDEX IF NOT EXISTS idx_chat_judge_evaluations_pipeline_decision
ON chat_judge_evaluations (pipeline, decision);
"""


class ChatJudgeRepository:
    def __init__(
        self,
        *,
        settings: Settings,
        database_path: str | None = None,
    ) -> None:
        self._settings = settings
        self._database_path = Path(database_path or settings.chat_judge_storage_path)
        self._logger = logging.getLogger(__name__)
        self._schema_lock = Lock()
        self._schema_ready = False

    @property
    def database_path(self) -> Path:
        return self._database_path

    def save(self, record: ChatJudgePersistenceRecord) -> ChatJudgePersistenceRecord:
        self._ensure_schema()
        payload = _serialize_record(record)
        self._logger.info(
            "💾 Chat judge persistence started.",
            extra={
                "judge_event": "chat_judge_repository.save_started",
                "storage": {
                    "backend": "sqlite",
                    "database_path": str(self._database_path),
                },
                "identifiers": {
                    "evaluation_id": record.evaluation_id,
                    "request_id": record.request_id,
                    "conversation_id": record.conversation_id,
                    "message_id": record.message_id,
                },
                "result": {
                    "overall_score": record.overall_score,
                    "decision": record.decision,
                    "approved": record.approved,
                },
            },
        )

        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO chat_judge_evaluations (
                        evaluation_id,
                        created_at,
                        model,
                        request_id,
                        conversation_id,
                        message_id,
                        idioma,
                        intencao,
                        pipeline,
                        handler,
                        summary,
                        improvements_json,
                        overall_score,
                        decision,
                        approved,
                        rejection_reasons_json,
                        coherence_score,
                        context_score,
                        correctness_score,
                        efficiency_score,
                        fidelity_score,
                        quality_score,
                        usefulness_score,
                        safety_score,
                        tone_of_voice_score,
                        weighted_contributions_json,
                        result_json
                    ) VALUES (
                        :evaluation_id,
                        :created_at,
                        :model,
                        :request_id,
                        :conversation_id,
                        :message_id,
                        :idioma,
                        :intencao,
                        :pipeline,
                        :handler,
                        :summary,
                        :improvements_json,
                        :overall_score,
                        :decision,
                        :approved,
                        :rejection_reasons_json,
                        :coherence_score,
                        :context_score,
                        :correctness_score,
                        :efficiency_score,
                        :fidelity_score,
                        :quality_score,
                        :usefulness_score,
                        :safety_score,
                        :tone_of_voice_score,
                        :weighted_contributions_json,
                        :result_json
                    )
                    """,
                    payload,
                )
        except sqlite3.Error as exc:
            self._logger.exception(
                "❌ Chat judge persistence failed.",
                extra={
                    "judge_event": "chat_judge_repository.save_failed",
                    "storage": {
                        "backend": "sqlite",
                        "database_path": str(self._database_path),
                    },
                    "identifiers": {
                        "evaluation_id": record.evaluation_id,
                        "request_id": record.request_id,
                        "conversation_id": record.conversation_id,
                        "message_id": record.message_id,
                    },
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            raise ServiceError("Falha ao persistir avaliacao do judge.", status_code=500) from exc

        self._logger.info(
            "✅ Chat judge persistence completed.",
            extra={
                "judge_event": "chat_judge_repository.saved",
                "storage": {
                    "backend": "sqlite",
                    "database_path": str(self._database_path),
                },
                "identifiers": {
                    "evaluation_id": record.evaluation_id,
                    "request_id": record.request_id,
                    "conversation_id": record.conversation_id,
                    "message_id": record.message_id,
                },
            },
        )
        return record

    def fetch_by_evaluation_id(self, evaluation_id: str) -> ChatJudgePersistenceRecord | None:
        self._ensure_schema()
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM chat_judge_evaluations WHERE evaluation_id = ?",
                    (evaluation_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            self._logger.exception(
                "❌ Chat judge persistence fetch failed.",
                extra={
                    "judge_event": "chat_judge_repository.fetch_failed",
                    "storage": {
                        "backend": "sqlite",
                        "database_path": str(self._database_path),
                    },
                    "identifiers": {"evaluation_id": evaluation_id},
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            raise ServiceError("Falha ao consultar avaliacao persistida do judge.", status_code=500) from exc

        if row is None:
            return None
        return _deserialize_record(dict(row))

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return

            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with self._connect() as connection:
                    connection.executescript(_CHAT_JUDGE_EVALUATIONS_SCHEMA_SQL)
            except sqlite3.Error as exc:
                self._logger.exception(
                    "❌ Chat judge persistence schema setup failed.",
                    extra={
                        "judge_event": "chat_judge_repository.schema_failed",
                        "storage": {
                            "backend": "sqlite",
                            "database_path": str(self._database_path),
                        },
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )
                raise ServiceError("Falha ao preparar schema da persistencia do judge.", status_code=500) from exc

            self._schema_ready = True
            self._logger.info(
                "🧱 Chat judge persistence schema ready.",
                extra={
                    "judge_event": "chat_judge_repository.schema_ready",
                    "storage": {
                        "backend": "sqlite",
                        "database_path": str(self._database_path),
                    },
                },
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._database_path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA synchronous=NORMAL;")
        return connection


def _serialize_record(record: ChatJudgePersistenceRecord) -> dict[str, Any]:
    return {
        "evaluation_id": record.evaluation_id,
        "created_at": record.created_at.isoformat(),
        "model": record.model,
        "request_id": record.request_id,
        "conversation_id": record.conversation_id,
        "message_id": record.message_id,
        "idioma": record.idioma,
        "intencao": record.intencao,
        "pipeline": record.pipeline,
        "handler": record.handler,
        "summary": record.summary,
        "improvements_json": json.dumps(record.improvements, ensure_ascii=False),
        "overall_score": record.overall_score,
        "decision": record.decision,
        "approved": 1 if record.approved else 0,
        "rejection_reasons_json": json.dumps(
            [reason.model_dump(mode="json") for reason in record.rejection_reasons],
            ensure_ascii=False,
        ),
        "coherence_score": record.coherence_score,
        "context_score": record.context_score,
        "correctness_score": record.correctness_score,
        "efficiency_score": record.efficiency_score,
        "fidelity_score": record.fidelity_score,
        "quality_score": record.quality_score,
        "usefulness_score": record.usefulness_score,
        "safety_score": record.safety_score,
        "tone_of_voice_score": record.tone_of_voice_score,
        "weighted_contributions_json": json.dumps(record.weighted_contributions, ensure_ascii=False),
        "result_json": json.dumps(record.result_payload, ensure_ascii=False),
    }


def _deserialize_record(row: dict[str, Any]) -> ChatJudgePersistenceRecord:
    rejection_reasons_raw = json.loads(row["rejection_reasons_json"])
    rejection_reasons = [ChatJudgeRejectionReason.model_validate(item) for item in rejection_reasons_raw]
    return ChatJudgePersistenceRecord(
        evaluation_id=row["evaluation_id"],
        created_at=row["created_at"],
        model=row["model"],
        request_id=row["request_id"],
        conversation_id=row["conversation_id"],
        message_id=row["message_id"],
        idioma=row["idioma"],
        intencao=row["intencao"],
        pipeline=row["pipeline"],
        handler=row["handler"],
        summary=row["summary"],
        improvements=json.loads(row["improvements_json"]),
        overall_score=row["overall_score"],
        decision=row["decision"],
        approved=bool(row["approved"]),
        rejection_reasons=rejection_reasons,
        coherence_score=row["coherence_score"],
        context_score=row["context_score"],
        correctness_score=row["correctness_score"],
        efficiency_score=row["efficiency_score"],
        fidelity_score=row["fidelity_score"],
        quality_score=row["quality_score"],
        usefulness_score=row["usefulness_score"],
        safety_score=row["safety_score"],
        tone_of_voice_score=row["tone_of_voice_score"],
        weighted_contributions=json.loads(row["weighted_contributions_json"]),
        result_payload=json.loads(row["result_json"]),
    )

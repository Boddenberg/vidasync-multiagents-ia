import json
from urllib.error import HTTPError

import pytest

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import ChatJudgeTrackingRecord
from vidasync_multiagents_ia.services.chat_judge_supabase_repository import (
    ChatJudgeSupabaseRepository,
)


class _FakeHTTPResponse:
    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_chat_judge_supabase_repository_upsert_retorna_registro(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def _fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        payload = json.loads(request.data.decode("utf-8"))
        captured["payload"] = payload
        return _FakeHTTPResponse(payload)

    monkeypatch.setattr(
        "vidasync_multiagents_ia.services.chat_judge_supabase_repository.urlopen",
        _fake_urlopen,
    )

    repository = ChatJudgeSupabaseRepository(
        settings=Settings(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
            chat_judge_supabase_table="llm_judge_evaluations",
            chat_judge_supabase_timeout_seconds=12.5,
        )
    )
    record = _build_tracking_record()

    stored = repository.upsert(record)

    assert stored == record
    assert captured["url"].endswith("/rest/v1/llm_judge_evaluations?on_conflict=evaluation_id")
    assert captured["timeout"] == 12.5
    assert captured["headers"]["Authorization"] == "Bearer service-role-key"
    assert captured["payload"][0]["evaluation_id"] == "eval-123"


def test_chat_judge_supabase_repository_lanca_erro_quando_supabase_retorna_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_urlopen(request, timeout):
        raise HTTPError(
            url=request.full_url,
            code=500,
            msg="Internal Server Error",
            hdrs=None,
            fp=_FakeHTTPResponse({"message": "boom"}),
        )

    monkeypatch.setattr(
        "vidasync_multiagents_ia.services.chat_judge_supabase_repository.urlopen",
        _fake_urlopen,
    )

    repository = ChatJudgeSupabaseRepository(
        settings=Settings(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-role-key",
        )
    )

    with pytest.raises(ServiceError, match="Supabase"):
        repository.upsert(_build_tracking_record())


def _build_tracking_record() -> ChatJudgeTrackingRecord:
    return ChatJudgeTrackingRecord.model_validate(
        {
            "evaluation_id": "eval-123",
            "created_at": "2026-03-26T18:00:00+00:00",
            "updated_at": "2026-03-26T18:00:00+00:00",
            "feature": "chat",
            "judge_status": "completed",
            "request_id": "req-123",
            "conversation_id": "conv-123",
            "message_id": "msg-123",
            "user_id": "user-123",
            "idioma": "pt-BR",
            "intencao": "perguntar_calorias",
            "pipeline": "resposta_conversacional_geral",
            "handler": "handler_responder_conversa_geral",
            "source_model": "gpt-4o-mini",
            "source_prompt": "Quantas calorias tem banana?",
            "source_response": "Banana media tem cerca de 90 kcal.",
            "source_duration_ms": 87.4,
            "source_prompt_chars": 29,
            "source_response_chars": 32,
            "source_metadata": {"canal": "app"},
            "judge_model": "gpt-4o-mini",
            "judge_duration_ms": 155.2,
            "judge_overall_score": 91.2,
            "judge_decision": "approved",
            "judge_summary": "Boa resposta.",
            "judge_scores": {
                "coherence": 5,
                "context": 4,
                "correctness": 5,
                "efficiency": 4,
                "fidelity": 5,
                "quality": 4,
                "usefulness": 4,
                "safety": 5,
                "tone_of_voice": 4,
            },
            "judge_improvements": ["Pode citar variacao por porcao."],
            "judge_rejection_reasons": [],
            "judge_result": {"approval": {"decision": "approved"}},
            "judge_error": None,
        }
    )

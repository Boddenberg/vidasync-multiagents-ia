import logging

import pytest

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import ChatJudgeEvaluationInput
from vidasync_multiagents_ia.services.chat_judge_llm_client import ChatJudgeLLMClient


class _FakeJudgeOpenAIClient:
    def __init__(self, *, payload: dict | None = None, error: Exception | None = None) -> None:
        self._payload = payload
        self._error = error
        self.calls: list[dict] = []

    def generate_json_from_text(self, *, model: str, system_prompt: str, user_prompt: str) -> dict:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )
        if self._error is not None:
            raise self._error
        assert self._payload is not None
        return self._payload


def test_chat_judge_llm_client_monta_prompt_e_valida_resposta(caplog: pytest.LogCaptureFixture) -> None:
    fake_client = _FakeJudgeOpenAIClient(payload=_valid_payload())
    service = ChatJudgeLLMClient(
        settings=Settings(
            openai_api_key="test-key",
            openai_model="gpt-4o-mini",
            chat_judge_model="gpt-4.1-mini",
        ),
        client=fake_client,  # type: ignore[arg-type]
    )
    request = ChatJudgeEvaluationInput(
        user_prompt="Quantas calorias tem uma banana?",
        assistant_response="Uma banana media tem cerca de 90 kcal.",
        conversation_id="conv-1",
        request_id="req-1",
        pipeline="guardrail_chat",
    )

    with caplog.at_level(logging.INFO):
        result = service.evaluate(request)

    assert result.criteria.correctness.score == 5
    assert fake_client.calls[0]["model"] == "gpt-4.1-mini"
    assert "Voce e um judge interno de qualidade" in fake_client.calls[0]["system_prompt"]
    assert "ENTRADA_DA_AVALIACAO_JSON" in fake_client.calls[0]["user_prompt"]
    assert any(getattr(record, "judge_event", None) == "chat_judge_llm.completed" for record in caplog.records)


def test_chat_judge_llm_client_converte_json_invalido_em_erro_claro(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_client = _FakeJudgeOpenAIClient(error=ValueError("invalid json"))
    service = ChatJudgeLLMClient(
        settings=Settings(openai_api_key="test-key", chat_judge_model="gpt-4o-mini"),
        client=fake_client,  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.INFO), pytest.raises(ServiceError) as exc:
        service.evaluate(
            {
                "user_prompt": "Oi",
                "assistant_response": "Ola",
            }
        )

    assert "json valido" in exc.value.message.lower()
    assert any(getattr(record, "judge_event", None) == "chat_judge_llm.invalid_json" for record in caplog.records)


def test_chat_judge_llm_client_rejeita_contrato_invalido(
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = _valid_payload()
    payload["criteria"].pop("fidelity")
    fake_client = _FakeJudgeOpenAIClient(payload=payload)
    service = ChatJudgeLLMClient(
        settings=Settings(openai_api_key="test-key", chat_judge_model="gpt-4o-mini"),
        client=fake_client,  # type: ignore[arg-type]
    )

    with caplog.at_level(logging.INFO), pytest.raises(ServiceError) as exc:
        service.evaluate(
            {
                "user_prompt": "Posso comer banana no lanche?",
                "assistant_response": "Sim, pode.",
            }
        )

    assert "contrato esperado" in exc.value.message.lower()
    assert "criteria.fidelity" in exc.value.message
    assert any(getattr(record, "judge_event", None) == "chat_judge_llm.schema_invalid" for record in caplog.records)


def _valid_payload() -> dict:
    return {
        "summary": "Resposta adequada e segura.",
        "criteria": {
            "coherence": {"score": 4, "reason": "Resposta consistente."},
            "context": {"score": 4, "reason": "Aderente ao pedido informado."},
            "correctness": {"score": 5, "reason": "Sem erro factual aparente."},
            "efficiency": {"score": 4, "reason": "Objetiva sem excessos."},
            "fidelity": {"score": 5, "reason": "Nao inventa dados."},
            "quality": {"score": 4, "reason": "Boa clareza geral."},
            "usefulness": {"score": 4, "reason": "Ajuda o usuario na pratica."},
            "safety": {"score": 5, "reason": "Sem risco identificado."},
            "tone_of_voice": {"score": 5, "reason": "Tom profissional e claro."},
        },
        "improvements": ["Pode citar limites quando faltar contexto."],
    }

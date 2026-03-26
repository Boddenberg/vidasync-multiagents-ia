import pytest

from vidasync_multiagents_ia.services.chat_judge_llm_parser import (
    ChatJudgeLLMParseError,
    parse_chat_judge_llm_payload,
    parse_chat_judge_llm_text,
)


def test_parse_chat_judge_llm_payload_valida_contrato_completo() -> None:
    result = parse_chat_judge_llm_payload(_valid_payload())

    assert result.summary == "Resposta adequada e segura."
    assert result.criteria.correctness.score == 5
    assert result.criteria.tone_of_voice.reason == "Tom profissional e claro."
    assert result.improvements == ["Pode citar limites quando faltar contexto."]


def test_parse_chat_judge_llm_payload_rejeita_estrutura_incompleta() -> None:
    payload = _valid_payload()
    payload["criteria"].pop("safety")

    with pytest.raises(ChatJudgeLLMParseError) as exc:
        parse_chat_judge_llm_payload(payload)

    assert "criteria.safety" in str(exc.value)


def test_parse_chat_judge_llm_text_rejeita_json_invalido() -> None:
    with pytest.raises(ChatJudgeLLMParseError) as exc:
        parse_chat_judge_llm_text('{"summary": "ok",}')

    assert "json valido" in str(exc.value).lower()


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

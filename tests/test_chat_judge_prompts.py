import json

import pytest

from vidasync_multiagents_ia.services.chat_judge_prompts import (
    CHAT_JUDGE_CRITERIA,
    build_chat_judge_input_payload,
    build_chat_judge_json_output_instruction,
    build_chat_judge_system_prompt,
    build_chat_judge_user_prompt,
)


def test_system_prompt_reforca_papel_restrito_do_judge() -> None:
    prompt = build_chat_judge_system_prompt()

    assert "nao responde ao usuario final" in prompt.lower()
    assert "apenas avalia" in prompt.lower()
    for criterion in CHAT_JUDGE_CRITERIA:
        assert criterion in prompt


def test_json_output_instruction_define_contrato_estrito() -> None:
    instruction = build_chat_judge_json_output_instruction()

    assert "somente um objeto json valido" in instruction.lower()
    assert "sem markdown" in instruction.lower()
    assert '"criteria"' in instruction
    assert '"improvements"' in instruction


def test_input_payload_normaliza_campos_opcionais_com_seguranca() -> None:
    payload = build_chat_judge_input_payload(
        user_prompt="  Quantas calorias tem uma banana?  ",
        assistant_response="  Uma banana media tem cerca de 90 kcal.  ",
        conversation_id="  conv-1  ",
        message_id="",
        request_id=None,
        idioma=None,
        intencao=" perguntar_calorias ",
        pipeline=" resposta_conversacional_geral ",
        handler=" handler_chat ",
        metadados_conversa={"canal": " app ", "vazio": "   "},
        roteamento_metadados=None,
        source_context={"docs": ["TBCA", None], "score": float("inf")},
    )

    assert payload["conversation_id"] == "conv-1"
    assert payload["message_id"] is None
    assert payload["request_id"] is None
    assert payload["idioma"] == "pt-BR"
    assert payload["intencao"] == "perguntar_calorias"
    assert payload["metadados_conversa"] == {"canal": "app", "vazio": None}
    assert payload["roteamento_metadados"] == {}
    assert payload["source_context"] == {"docs": ["TBCA", None], "score": None}


def test_user_prompt_embute_payload_json_valido_sem_none_pythonico() -> None:
    prompt = build_chat_judge_user_prompt(
        user_prompt="Quero sugestao de lanche pos treino.",
        assistant_response="Voce pode usar iogurte com fruta e aveia.",
        conversation_id="conv-9",
        metadados_conversa={"canal": "chat"},
        source_context=["doc_a", "doc_b"],
    )

    assert "ENTRADA_DA_AVALIACAO_JSON:" in prompt
    assert "INSTRUCAO_DE_SAIDA_JSON:" in prompt
    assert "None" not in prompt

    payload_fragment = prompt.split("ENTRADA_DA_AVALIACAO_JSON:\n", maxsplit=1)[1]
    payload_json = payload_fragment.split("\n\nINSTRUCAO_DE_SAIDA_JSON:\n", maxsplit=1)[0]
    parsed = json.loads(payload_json)

    assert parsed["conversation_id"] == "conv-9"
    assert parsed["metadados_conversa"] == {"canal": "chat"}
    assert parsed["source_context"] == ["doc_a", "doc_b"]


@pytest.mark.parametrize("field_name", ["user_prompt", "assistant_response"])
def test_builder_exige_campos_obrigatorios(field_name: str) -> None:
    kwargs = {
        "user_prompt": "pedido valido",
        "assistant_response": "resposta valida",
    }
    kwargs[field_name] = "   "

    with pytest.raises(ValueError):
        build_chat_judge_input_payload(**kwargs)

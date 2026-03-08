from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.services.chat_substituicoes_flow_service import (
    ChatSubstituicoesFlowService,
)
from vidasync_multiagents_ia.services.chat_tools import ChatToolExecutionOutput


class _FakeOpenAIClientProfileSuccess:
    def generate_json_from_text(self, *, model: str, system_prompt: str, user_prompt: str):
        assert model == "gpt-4o-mini"
        return {
            "alimento_original": "arroz branco",
            "objetivo_troca": "emagrecimento",
            "contexto_refeicao": "almoco",
            "restricoes": ["sem lactose"],
            "preferencias": ["praticidade"],
            "alimentos_evitar": [],
            "observacoes_usuario": "quero algo rapido",
        }


class _FakeOpenAIClientProfileWeak:
    def generate_json_from_text(self, *, model: str, system_prompt: str, user_prompt: str):
        return {
            "alimento_original": None,
            "objetivo_troca": None,
            "contexto_refeicao": None,
            "restricoes": [],
            "preferencias": [],
            "alimentos_evitar": [],
            "observacoes_usuario": None,
        }


def test_chat_substituicoes_flow_prioriza_regras_quando_perfil_e_claro() -> None:
    tool_calls = {"count": 0}

    def _tool_runner(prompt: str, idioma: str) -> ChatToolExecutionOutput:
        tool_calls["count"] += 1
        return ChatToolExecutionOutput(
            tool_name="sugerir_substituicoes",
            status="sucesso",
            resposta="fallback",
        )

    service = ChatSubstituicoesFlowService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=_FakeOpenAIClientProfileSuccess(),  # type: ignore[arg-type]
        tool_runner=_tool_runner,
    )

    output = service.executar(prompt="Quero trocar arroz branco por algo mais leve.", idioma="pt-BR")

    assert output.precisa_revisao is False
    assert output.warnings == []
    assert tool_calls["count"] == 0
    assert output.metadados["flow"] == "substituicoes_alimentares_v1"
    assert len(output.metadados["substituicoes_regra"]) >= 2
    assert "Alimento original: arroz branco" in output.resposta


def test_chat_substituicoes_flow_aciona_tool_quando_contexto_insuficiente() -> None:
    tool_calls = {"count": 0}

    def _tool_runner(prompt: str, idioma: str) -> ChatToolExecutionOutput:
        tool_calls["count"] += 1
        return ChatToolExecutionOutput(
            tool_name="sugerir_substituicoes",
            status="sucesso",
            resposta="Sugestoes adicionais: troque por versoes integrais e ajuste porcoes.",
            warnings=[],
        )

    service = ChatSubstituicoesFlowService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=_FakeOpenAIClientProfileWeak(),  # type: ignore[arg-type]
        tool_runner=_tool_runner,
    )

    output = service.executar(prompt="Pode sugerir trocas para minha dieta?", idioma="pt-BR")

    assert tool_calls["count"] == 1
    assert output.metadados["tool_fallback_utilizada"] is True
    assert any("alimento original" in warning.lower() for warning in output.warnings)
    assert "Complemento contextual (tool):" in output.resposta


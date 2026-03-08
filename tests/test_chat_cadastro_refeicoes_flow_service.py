from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.services.chat_cadastro_refeicoes_flow_service import (
    ChatCadastroRefeicoesFlowService,
)
from vidasync_multiagents_ia.services.chat_tools import ChatToolExecutionOutput


class _FakeOpenAIClientSuccess:
    def generate_json_from_text(self, *, model: str, system_prompt: str, user_prompt: str):
        assert model == "gpt-4o-mini"
        return {
            "tipo_registro": "refeicao",
            "nome_registro": "almoco",
            "refeicao_tipo": "almoco",
            "itens": [
                {
                    "nome_alimento": "arroz",
                    "quantidade_texto": "120 g",
                    "quantidade_valor": 120,
                    "unidade": "g",
                    "quantidade_gramas": 120,
                    "confianca_extracao": 0.92,
                    "ambiguidade": None,
                },
                {
                    "nome_alimento": "frango grelhado",
                    "quantidade_texto": "100 g",
                    "quantidade_valor": 100,
                    "unidade": "g",
                    "quantidade_gramas": 100,
                    "confianca_extracao": 0.9,
                    "ambiguidade": None,
                },
            ],
            "observacoes": None,
        }


class _FakeOpenAIClientAmbiguous:
    def generate_json_from_text(self, *, model: str, system_prompt: str, user_prompt: str):
        return {
            "tipo_registro": "indefinido",
            "nome_registro": None,
            "refeicao_tipo": None,
            "itens": [
                {
                    "nome_alimento": "salada",
                    "quantidade_texto": None,
                    "quantidade_valor": None,
                    "unidade": None,
                    "quantidade_gramas": None,
                    "confianca_extracao": 0.5,
                    "ambiguidade": "Quantidade nao informada.",
                }
            ],
            "observacoes": "incerto",
        }


class _FakeOpenAIClientFailure:
    def generate_json_from_text(self, *, model: str, system_prompt: str, user_prompt: str):
        raise RuntimeError("falha llm")


def test_fluxo_cadastro_refeicoes_sucesso_sem_revisao() -> None:
    service = ChatCadastroRefeicoesFlowService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=_FakeOpenAIClientSuccess(),  # type: ignore[arg-type]
    )

    output = service.executar(prompt="Cadastre meu almoco: 120 g arroz, 100 g frango grelhado.")

    assert output.precisa_revisao is False
    assert output.warnings == []
    assert output.metadados["flow"] == "cadastro_refeicoes_texto_v1"
    assert output.metadados["confianca_media"] == 0.91
    assert len(output.metadados["cadastro_extraido"]["itens"]) == 2
    assert "Cadastro pronto para confirmacao" in output.resposta


def test_fluxo_cadastro_refeicoes_pede_confirmacao_em_ambiguidade() -> None:
    service = ChatCadastroRefeicoesFlowService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=_FakeOpenAIClientAmbiguous(),  # type: ignore[arg-type]
    )

    output = service.executar(prompt="Cadastre refeicao incerta.")

    assert output.precisa_revisao is True
    assert any("ambiguidade" in warning.lower() for warning in output.warnings)
    assert any("Confianca de extracao baixa" in warning for warning in output.warnings)
    assert len(output.metadados["perguntas_confirmacao"]) >= 1
    assert "Preciso confirmar antes de salvar" in output.resposta


def test_fluxo_cadastro_refeicoes_usa_fallback_tool_quando_nao_ha_itens() -> None:
    calls = {"count": 0}

    def _tool_runner(prompt: str, idioma: str) -> ChatToolExecutionOutput:
        calls["count"] += 1
        return ChatToolExecutionOutput(
            tool_name="cadastrar_prato",
            status="parcial",
            resposta="Rascunho de cadastro montado por tool.",
            warnings=["Itens do prato nao identificados; revise antes de salvar."],
            precisa_revisao=True,
            metadados={"prato": {"nome_prato": None, "itens": []}},
        )

    service = ChatCadastroRefeicoesFlowService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=_FakeOpenAIClientFailure(),  # type: ignore[arg-type]
        tool_runner=_tool_runner,
    )

    output = service.executar(prompt="Cadastre minha refeicao de hoje.")

    assert calls["count"] == 1
    assert output.precisa_revisao is True
    assert output.metadados["tool_fallback"] is not None
    assert any("fallback" in warning.lower() for warning in output.warnings)

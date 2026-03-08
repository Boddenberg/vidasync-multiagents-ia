from langchain_core.documents import Document

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.services.chat_receitas_flow_service import ChatReceitasFlowService


class _FakeOpenAIClientSuccess:
    def generate_json_from_text(self, *, model: str, system_prompt: str, user_prompt: str):
        assert model == "gpt-4o-mini"
        if "Extraia do texto os campos" in user_prompt:
            return {
                "preferencias": ["frango", "praticidade"],
                "restricoes": ["sem lactose"],
                "objetivo_nutricional": "emagrecimento",
                "contexto_refeicao": "jantar",
                "ingredientes_disponiveis": ["frango", "abobrinha"],
                "tempo_max_preparo_min": 25,
                "observacoes_usuario": "evitar fritura",
            }
        return {
            "receitas": [
                {
                    "nome": "Frango com abobrinha na frigideira",
                    "motivo_aderencia": "rica em proteina e facil de preparar",
                    "tempo_preparo_min": 20,
                    "rendimento_porcoes": "2 porcoes",
                    "ingredientes": ["frango", "abobrinha", "alho"],
                    "preparo_passos": ["cortar", "temperar", "grelhar", "servir"],
                    "ajuste_objetivo": "reduzir oleo e manter porcao de carbo controlada",
                },
                {
                    "nome": "Sopa cremosa de legumes com frango",
                    "motivo_aderencia": "saciedade com baixo teor calorico",
                    "tempo_preparo_min": 25,
                    "rendimento_porcoes": "3 porcoes",
                    "ingredientes": ["frango", "cenoura", "abobrinha"],
                    "preparo_passos": ["cozinhar", "bater parte dos legumes", "finalizar"],
                    "ajuste_objetivo": "priorizar vegetais no prato",
                },
            ],
            "dicas_preparo": ["deixe frango temperado no dia anterior"],
            "lista_compras": ["frango", "abobrinha", "alho"],
            "observacoes": ["ajuste sal conforme preferencia"],
        }


class _FakeOpenAIClientFallbackProfile:
    def __init__(self) -> None:
        self._calls = 0

    def generate_json_from_text(self, *, model: str, system_prompt: str, user_prompt: str):
        self._calls += 1
        if self._calls == 1:
            raise ValueError("falha perfil")
        return {
            "receitas": [
                {
                    "nome": "Omelete de forno",
                    "ingredientes": ["ovo", "tomate"],
                    "preparo_passos": ["misturar", "assar"],
                }
            ]
        }


def test_chat_receitas_flow_service_monta_resposta_organizada() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = ChatReceitasFlowService(
        settings=settings,
        client=_FakeOpenAIClientSuccess(),  # type: ignore[arg-type]
        rag_context_builder=lambda _: (
            "doc receitas e boas praticas",
            [Document(page_content="contexto nutricional", metadata={"source_path": "knowledge/faq.md"})],
        ),
    )

    output = service.executar(prompt="Quero receitas sem lactose para jantar e emagrecer.")

    assert output.precisa_revisao is False
    assert output.warnings == []
    assert "Sugestao de receitas personalizada" in output.resposta
    assert output.metadados["flow"] == "receitas_personalizadas_v1"
    assert output.metadados["perfil"]["objetivo_nutricional"] == "emagrecimento"
    assert len(output.metadados["receitas"]) == 2
    assert output.metadados["fontes_rag"] == 1


def test_chat_receitas_flow_service_aplica_fallback_no_perfil() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = ChatReceitasFlowService(
        settings=settings,
        client=_FakeOpenAIClientFallbackProfile(),  # type: ignore[arg-type]
        rag_context_builder=lambda _: ("", []),
    )

    output = service.executar(prompt="Quero receita sem gluten em 20 min.")

    assert any("fallback heuristico" in warning for warning in output.warnings)
    assert any("Base RAG sem documentos" in warning for warning in output.warnings)
    assert len(output.metadados["receitas"]) == 1


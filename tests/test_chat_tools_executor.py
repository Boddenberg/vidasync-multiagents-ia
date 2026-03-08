from datetime import datetime, timezone

from langchain_core.documents import Document

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.schemas import (
    AgenteCaloriasTexto,
    CaloriasTextoResponse,
    IntencaoChatDetectada,
    ItemCaloriasTexto,
    TotaisCaloriasTexto,
)
from vidasync_multiagents_ia.services.chat_tools import (
    ChatToolExecutionInput,
    build_chat_tool_executor,
)


class _FakeOpenAIClient:
    def generate_text(self, *, model: str, prompt: str) -> str:
        assert model == "gpt-4o-mini"
        assert prompt
        return "resposta llm ferramenta"


class _FakeCaloriasTextoService:
    def calcular(
        self,
        *,
        texto: str,
        contexto: str = "calcular_calorias_texto",
        idioma: str = "pt-BR",
    ) -> CaloriasTextoResponse:
        assert texto
        return CaloriasTextoResponse(
            contexto=contexto,
            idioma=idioma,
            texto=texto,
            itens=[
                ItemCaloriasTexto(
                    alimento="banana",
                    calorias_kcal=89.0,
                    carboidratos_g=22.8,
                    proteina_g=1.1,
                    lipidios_g=0.3,
                    confianca=0.92,
                )
            ],
            totais=TotaisCaloriasTexto(
                calorias_kcal=89.0,
                carboidratos_g=22.8,
                proteina_g=1.1,
                lipidios_g=0.3,
            ),
            warnings=[],
            agente=AgenteCaloriasTexto(
                contexto="calcular_calorias_texto",
                nome_agente="agente_calculo_calorias_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca_media=0.92,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def _intencao_padrao() -> IntencaoChatDetectada:
    return IntencaoChatDetectada(
        intencao="pedir_dicas",
        confianca=0.82,
        contexto_roteamento="chat_dicas",
        requer_fluxo_estruturado=False,
    )


def test_chat_tools_executor_cobre_set_inicial_de_tools() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    executor = build_chat_tool_executor(
        settings=settings,
        client=_FakeOpenAIClient(),  # type: ignore[arg-type]
        calorias_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
        rag_retriever=lambda _: [Document(page_content="base", metadata={"source": "test"})],
    )
    intencao = _intencao_padrao()

    casos = [
        ("calcular_calorias", "calorias de banana"),
        ("calcular_macros", "macros de banana"),
        ("calcular_imc", "calcule meu imc 72 kg 1,75 m"),
        ("buscar_receitas", "receitas com frango"),
        ("sugerir_substituicoes", "substituicoes para arroz"),
        ("cadastrar_prato", "prato: omelete, ovo, queijo"),
        ("consultar_conhecimento_nutricional", "o que e fibra alimentar?"),
    ]

    for tool_name, prompt in casos:
        result = executor.execute(
            data=ChatToolExecutionInput(
                tool_name=tool_name,  # type: ignore[arg-type]
                prompt=prompt,
                idioma="pt-BR",
                intencao=intencao,
            )
        )
        assert result.tool_name == tool_name
        assert result.resposta
        assert result.status in {"sucesso", "parcial", "erro"}


def test_tool_calcular_imc_retorna_parcial_quando_dado_insuficiente() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    executor = build_chat_tool_executor(
        settings=settings,
        client=_FakeOpenAIClient(),  # type: ignore[arg-type]
        calorias_service=_FakeCaloriasTextoService(),  # type: ignore[arg-type]
        rag_retriever=lambda _: [Document(page_content="base", metadata={"source": "test"})],
    )

    result = executor.execute(
        data=ChatToolExecutionInput(
            tool_name="calcular_imc",
            prompt="calcule meu imc",
            idioma="pt-BR",
            intencao=_intencao_padrao(),
        )
    )

    assert result.status == "parcial"
    assert result.precisa_revisao is True
    assert "campos_faltantes" in result.metadados

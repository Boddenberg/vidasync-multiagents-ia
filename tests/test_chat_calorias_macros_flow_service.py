from datetime import datetime, timezone

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    AgenteCaloriasTexto,
    CaloriasTextoResponse,
    FonteCaloriasConsulta,
    ItemCaloriasTexto,
    SelecaoFonteCalorias,
    TotaisCaloriasTexto,
)
from vidasync_multiagents_ia.services.chat_calorias_macros_flow_service import (
    ChatCaloriasMacrosFlowService,
)
from vidasync_multiagents_ia.services.chat_tools import ChatToolExecutionInput, ChatToolExecutionOutput


class _FakeToolExecutor:
    def __init__(self) -> None:
        self.calls: list[ChatToolExecutionInput] = []

    def execute(self, data: ChatToolExecutionInput) -> ChatToolExecutionOutput:
        self.calls.append(data)
        if data.tool_name == "consultar_conhecimento_nutricional":
            return ChatToolExecutionOutput(
                tool_name=data.tool_name,
                status="sucesso",
                resposta="Caloria e a energia total do alimento.",
            )
        if data.tool_name == "calcular_macros":
            return ChatToolExecutionOutput(
                tool_name=data.tool_name,
                status="sucesso",
                resposta="Macros estimados para a entrada.",
            )
        return ChatToolExecutionOutput(
            tool_name=data.tool_name,
            status="sucesso",
            resposta="Calorias estimadas para a entrada.",
        )


class _FakeCaloriasService:
    def __init__(self, *, response: CaloriasTextoResponse | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[str] = []

    def calcular(
        self,
        *,
        texto: str,
        contexto: str = "calcular_calorias_texto",
        idioma: str = "pt-BR",
    ) -> CaloriasTextoResponse:
        self.calls.append(texto)
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _build_calorias_response() -> CaloriasTextoResponse:
    return CaloriasTextoResponse(
        contexto="calcular_calorias_texto",
        idioma="pt-BR",
        texto="150 g de banana",
        itens=[
            ItemCaloriasTexto(
                descricao_original="150 g de banana",
                alimento="Banana prata crua",
                quantidade_texto="150 g",
                calorias_kcal=135.0,
                proteina_g=1.8,
                carboidratos_g=30.0,
                lipidios_g=0.3,
                confianca=0.91,
            )
        ],
        totais=TotaisCaloriasTexto(
            calorias_kcal=135.0,
            proteina_g=1.8,
            carboidratos_g=30.0,
            lipidios_g=0.3,
        ),
        warnings=[],
        fontes_consultadas=[
            FonteCaloriasConsulta(
                fonte="TABELA_TACO_ONLINE",
                item="Banana prata crua",
                calorias_kcal=135.0,
                proteina_g=1.8,
                carboidratos_g=30.0,
                lipidios_g=0.3,
                confianca=0.91,
            ),
            FonteCaloriasConsulta(
                fonte="OPEN_FOOD_FACTS",
                item="Banana pacote",
                calorias_kcal=132.0,
                proteina_g=1.7,
                carboidratos_g=29.0,
                lipidios_g=0.2,
                confianca=0.84,
            ),
        ],
        selecao_fonte=SelecaoFonteCalorias(
            fonte_escolhida="TABELA_TACO_ONLINE",
            confianca=0.9,
            justificativa="Maior coerencia com alimento in natura.",
            agente_seletor_acionado=True,
        ),
        agente=AgenteCaloriasTexto(
            contexto="calcular_calorias_texto",
            nome_agente="agente_calculo_calorias_texto",
            status="sucesso",
            modelo="gpt-4o-mini",
            confianca_media=0.91,
        ),
        extraido_em=datetime.now(timezone.utc),
    )


def test_fluxo_usa_tool_contextual_para_pergunta_conceitual() -> None:
    tool_executor = _FakeToolExecutor()
    calorias_service = _FakeCaloriasService(response=_build_calorias_response())
    service = ChatCaloriasMacrosFlowService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        tool_executor=tool_executor,  # type: ignore[arg-type]
        calorias_service=calorias_service,  # type: ignore[arg-type]
    )

    output = service.executar(prompt="O que e caloria e macro?", idioma="pt-BR")

    assert output.metadados["route"] == "apoio_contextual"
    assert output.handler_override == "handler_tool_consultar_conhecimento_nutricional"
    assert output.resposta == "Caloria e a energia total do alimento."
    assert len(tool_executor.calls) == 1
    assert len(calorias_service.calls) == 0


def test_fluxo_usa_base_estruturada_dual_fontes_para_alimento_unico() -> None:
    tool_executor = _FakeToolExecutor()
    calorias_service = _FakeCaloriasService(response=_build_calorias_response())
    service = ChatCaloriasMacrosFlowService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        tool_executor=tool_executor,  # type: ignore[arg-type]
        calorias_service=calorias_service,  # type: ignore[arg-type]
    )

    output = service.executar(prompt="Quantas calorias tem banana em 150 g?", idioma="pt-BR")

    assert output.metadados["route"] == "base_estruturada_dual_taco_open_food_facts"
    assert output.metadados["fonte"] == "TABELA_TACO_ONLINE"
    assert output.handler_override == "handler_base_estruturada_calorias_dual_fontes"
    assert "Resultado por base estruturada (TACO + Open Food Facts)" in output.resposta
    assert len(tool_executor.calls) == 0
    assert calorias_service.calls == ["150 g de banana"]


def test_fluxo_faz_fallback_para_tool_quando_base_estruturada_dual_falha() -> None:
    tool_executor = _FakeToolExecutor()
    calorias_service = _FakeCaloriasService(error=ServiceError("nao encontrado", status_code=404))
    service = ChatCaloriasMacrosFlowService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        tool_executor=tool_executor,  # type: ignore[arg-type]
        calorias_service=calorias_service,  # type: ignore[arg-type]
    )

    output = service.executar(prompt="Quais os macros de banana em 150 g?", idioma="pt-BR")

    assert output.metadados["route"] == "tool_calcular_macros"
    assert output.metadados["route_fallback_applied"] is True
    assert output.handler_override == "handler_tool_calcular_macros"
    assert output.precisa_revisao is True
    assert any("Base estruturada indisponivel" in warning for warning in output.warnings)
    assert len(tool_executor.calls) == 1
    assert tool_executor.calls[0].tool_name == "calcular_macros"
    assert calorias_service.calls == ["150 g de banana"]

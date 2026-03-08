from datetime import datetime, timezone

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    TBCAFoodSelection,
    TBCAMacros,
    TBCASearchResponse,
    TacoOnlineFoodResponse,
    TacoOnlineNutrients,
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


class _FakeTBCAService:
    def __init__(self, *, response: TBCASearchResponse | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[str, float]] = []

    def search(self, query: str, grams: float) -> TBCASearchResponse:
        self.calls.append((query, grams))
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


class _FakeTacoService:
    def __init__(self, *, response: TacoOnlineFoodResponse | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[str, float]] = []

    def get_food(self, *, query: str | None = None, grams: float = 100.0, **_: object) -> TacoOnlineFoodResponse:
        self.calls.append((query or "", grams))
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _build_tbca_response(*, grams: float = 100.0) -> TBCASearchResponse:
    return TBCASearchResponse(
        consulta="banana",
        gramas=grams,
        alimento_selecionado=TBCAFoodSelection(
            codigo="BRC1",
            nome="Banana, prata, crua",
            url_detalhe="https://www.tbca.net.br/base-dados/int_composicao_alimentos.php?foo=bar",
        ),
        por_100g=TBCAMacros(
            energia_kcal=98.0,
            proteina_g=1.3,
            carboidratos_g=26.0,
            lipidios_g=0.1,
        ),
        ajustado=TBCAMacros(
            energia_kcal=round(98.0 * (grams / 100.0), 4),
            proteina_g=round(1.3 * (grams / 100.0), 4),
            carboidratos_g=round(26.0 * (grams / 100.0), 4),
            lipidios_g=round(0.1 * (grams / 100.0), 4),
        ),
    )


def _build_taco_response(*, grams: float = 100.0) -> TacoOnlineFoodResponse:
    per_100g = TacoOnlineNutrients(
        energia_kcal=90.0,
        proteina_g=1.1,
        carboidratos_g=20.0,
        lipidios_g=0.2,
    )
    return TacoOnlineFoodResponse(
        url_pagina="https://www.tabelatacoonline.com.br/tabela-nutricional/taco/banana-prata-crua",
        slug="banana-prata-crua",
        gramas=grams,
        nome_alimento="Banana prata crua",
        grupo_alimentar="Frutas",
        base_calculo="100 gramas",
        por_100g=per_100g,
        ajustado=TacoOnlineNutrients(
            energia_kcal=round((per_100g.energia_kcal or 0.0) * (grams / 100.0), 4),
            proteina_g=round((per_100g.proteina_g or 0.0) * (grams / 100.0), 4),
            carboidratos_g=round((per_100g.carboidratos_g or 0.0) * (grams / 100.0), 4),
            lipidios_g=round((per_100g.lipidios_g or 0.0) * (grams / 100.0), 4),
        ),
        extraido_em=datetime.now(timezone.utc),
    )


def test_fluxo_usa_tool_contextual_para_pergunta_conceitual() -> None:
    tool_executor = _FakeToolExecutor()
    tbca_service = _FakeTBCAService(response=_build_tbca_response())
    taco_service = _FakeTacoService(response=_build_taco_response())
    service = ChatCaloriasMacrosFlowService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        tool_executor=tool_executor,  # type: ignore[arg-type]
        tbca_service=tbca_service,  # type: ignore[arg-type]
        taco_online_service=taco_service,  # type: ignore[arg-type]
    )

    output = service.executar(prompt="O que e caloria e macro?", idioma="pt-BR")

    assert output.metadados["route"] == "apoio_contextual"
    assert output.handler_override == "handler_tool_consultar_conhecimento_nutricional"
    assert output.resposta == "Caloria e a energia total do alimento."
    assert len(tool_executor.calls) == 1
    assert len(tbca_service.calls) == 0
    assert len(taco_service.calls) == 0


def test_fluxo_usa_base_estruturada_tbca_para_alimento_unico() -> None:
    tool_executor = _FakeToolExecutor()
    tbca_service = _FakeTBCAService(response=_build_tbca_response(grams=150.0))
    taco_service = _FakeTacoService(response=_build_taco_response(grams=150.0))
    service = ChatCaloriasMacrosFlowService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        tool_executor=tool_executor,  # type: ignore[arg-type]
        tbca_service=tbca_service,  # type: ignore[arg-type]
        taco_online_service=taco_service,  # type: ignore[arg-type]
    )

    output = service.executar(prompt="Quantas calorias tem banana em 150 g?", idioma="pt-BR")

    assert output.metadados["route"] == "base_estruturada_tbca"
    assert output.metadados["fonte"] == "TBCA"
    assert output.handler_override == "handler_base_estruturada_calorias_tbca"
    assert "Resultado por base estruturada (TBCA)" in output.resposta
    assert len(tool_executor.calls) == 0
    assert tbca_service.calls == [("banana", 150.0)]


def test_fluxo_faz_fallback_para_tool_quando_bases_estruturadas_falham() -> None:
    tool_executor = _FakeToolExecutor()
    tbca_service = _FakeTBCAService(error=ServiceError("nao encontrado", status_code=404))
    taco_service = _FakeTacoService(error=ServiceError("nao encontrado", status_code=404))
    service = ChatCaloriasMacrosFlowService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        tool_executor=tool_executor,  # type: ignore[arg-type]
        tbca_service=tbca_service,  # type: ignore[arg-type]
        taco_online_service=taco_service,  # type: ignore[arg-type]
    )

    output = service.executar(prompt="Quais os macros de banana em 150 g?", idioma="pt-BR")

    assert output.metadados["route"] == "tool_calcular_macros"
    assert output.metadados["route_fallback_applied"] is True
    assert output.handler_override == "handler_tool_calcular_macros"
    assert output.precisa_revisao is True
    assert any("Base estruturada indisponivel" in warning for warning in output.warnings)
    assert len(tool_executor.calls) == 1
    assert tool_executor.calls[0].tool_name == "calcular_macros"
    assert tbca_service.calls == [("banana", 150.0)]
    assert taco_service.calls == [("banana", 150.0)]

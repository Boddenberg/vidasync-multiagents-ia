from datetime import datetime, timezone

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    OpenFoodFactsNutrients,
    OpenFoodFactsProduct,
    OpenFoodFactsSearchResponse,
    TacoOnlineFoodResponse,
    TacoOnlineNutrients,
)
from vidasync_multiagents_ia.services.calorias_texto_service import CaloriasTextoService


class _FakeOpenAIClient:
    def __init__(self, *, selector_payload: dict | None = None, llm_payload: dict | None = None) -> None:
        self.selector_payload = selector_payload or {}
        self.llm_payload = llm_payload or {}
        self.calls: list[dict[str, str]] = []

    def generate_json_from_text(self, *, model: str, system_prompt: str, user_prompt: str) -> dict:
        self.calls.append({"model": model, "system_prompt": system_prompt, "user_prompt": user_prompt})
        if "agente seletor de confianca nutricional" in system_prompt.lower():
            return self.selector_payload
        return self.llm_payload


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


class _FakeOpenFoodFactsService:
    def __init__(self, *, response: OpenFoodFactsSearchResponse | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[str, float]] = []

    def search(
        self,
        *,
        query: str,
        grams: float = 100.0,
        page: int = 1,
        page_size: int = 10,
    ) -> OpenFoodFactsSearchResponse:
        self.calls.append((query, grams))
        if self._error is not None:
            raise self._error
        assert self._response is not None
        assert page == 1
        assert page_size == 5
        return self._response


def _build_taco_response(*, grams: float, energy_kcal: float) -> TacoOnlineFoodResponse:
    per_100g = TacoOnlineNutrients(
        energia_kcal=round(energy_kcal / (grams / 100.0), 4),
        proteina_g=1.0,
        carboidratos_g=11.0,
        lipidios_g=0.0,
    )
    adjusted = TacoOnlineNutrients(
        energia_kcal=energy_kcal,
        proteina_g=round(1.0 * (grams / 100.0), 4),
        carboidratos_g=round(11.0 * (grams / 100.0), 4),
        lipidios_g=0.0,
    )
    return TacoOnlineFoodResponse(
        url_pagina="https://www.tabelatacoonline.com.br/tabela-nutricional/taco/bebida-energetica",
        slug="bebida-energetica",
        gramas=grams,
        nome_alimento="Bebida energetica",
        grupo_alimentar="Bebidas",
        base_calculo="100 gramas",
        por_100g=per_100g,
        ajustado=adjusted,
        extraido_em=datetime.now(timezone.utc),
    )


def _build_off_response(*, query: str, grams: float, energy_kcal: float) -> OpenFoodFactsSearchResponse:
    per_100g = OpenFoodFactsNutrients(
        energia_kcal=round(energy_kcal / (grams / 100.0), 4),
        proteina_g=0.0,
        carboidratos_g=12.0,
        lipidios_g=0.0,
    )
    adjusted = OpenFoodFactsNutrients(
        energia_kcal=energy_kcal,
        proteina_g=0.0,
        carboidratos_g=round(12.0 * (grams / 100.0), 4),
        lipidios_g=0.0,
    )
    return OpenFoodFactsSearchResponse(
        consulta=query,
        gramas=grams,
        page=1,
        page_size=5,
        total_produtos=1,
        produtos=[
            OpenFoodFactsProduct(
                codigo_barras="123",
                nome_produto="Monster Energy Ultra",
                marcas="Monster",
                por_100g=per_100g,
                ajustado=adjusted,
            )
        ],
        extraido_em=datetime.now(timezone.utc),
    )


def test_calorias_texto_service_usa_fontes_em_paralelo_e_seletor() -> None:
    query = "bebida energetica"
    grams = 500.0
    openai_client = _FakeOpenAIClient(
        selector_payload={
            "fonte_escolhida": "OPEN_FOOD_FACTS",
            "confianca": 0.88,
            "justificativa": "Produto industrializado mais aderente ao item.",
        }
    )
    service = CaloriasTextoService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=openai_client,  # type: ignore[arg-type]
        taco_online_service=_FakeTacoService(response=_build_taco_response(grams=grams, energy_kcal=210.0)),  # type: ignore[arg-type]
        open_food_facts_service=_FakeOpenFoodFactsService(
            response=_build_off_response(query=query, grams=grams, energy_kcal=225.0)
        ),  # type: ignore[arg-type]
    )

    result = service.calcular(texto="500 g de bebida energetica")

    assert len(result.fontes_consultadas) == 2
    assert result.selecao_fonte is not None
    assert result.selecao_fonte.fonte_escolhida == "OPEN_FOOD_FACTS"
    assert result.itens[0].calorias_kcal == 225.0
    assert result.totais.calorias_kcal == 225.0
    assert len(openai_client.calls) == 1


def test_calorias_texto_service_faz_fallback_para_llm_quando_fontes_falham() -> None:
    llm_payload = {
        "itens": [
            {
                "descricao_original": "150 g de banana",
                "alimento": "banana",
                "quantidade_texto": "150 g",
                "calorias_kcal": 133.5,
                "proteina_g": 1.5,
                "carboidratos_g": 34.5,
                "lipidios_g": 0.3,
                "confianca": 0.8,
            }
        ],
        "totais": {
            "calorias_kcal": 133.5,
            "proteina_g": 1.5,
            "carboidratos_g": 34.5,
            "lipidios_g": 0.3,
        },
        "warnings": [],
    }
    openai_client = _FakeOpenAIClient(llm_payload=llm_payload)
    taco = _FakeTacoService(error=ServiceError("nao encontrado", status_code=404))
    off = _FakeOpenFoodFactsService(error=ServiceError("nao encontrado", status_code=404))
    service = CaloriasTextoService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=openai_client,  # type: ignore[arg-type]
        taco_online_service=taco,  # type: ignore[arg-type]
        open_food_facts_service=off,  # type: ignore[arg-type]
    )

    result = service.calcular(texto="150 g de banana")

    assert result.itens[0].alimento == "banana"
    assert result.totais.calorias_kcal == 133.5
    assert result.fontes_consultadas == []
    assert result.selecao_fonte is None
    assert taco.calls == [("banana", 150.0)]
    assert off.calls == [("banana", 150.0)]
    assert len(openai_client.calls) == 1


def test_calorias_texto_service_nao_consulta_fontes_para_texto_combinado() -> None:
    llm_payload = {
        "itens": [
            {"alimento": "arroz", "calorias_kcal": 130},
            {"alimento": "feijao", "calorias_kcal": 90},
        ],
        "totais": {"calorias_kcal": 220},
        "warnings": [],
    }
    openai_client = _FakeOpenAIClient(llm_payload=llm_payload)
    taco = _FakeTacoService(error=ServiceError("nao encontrado", status_code=404))
    off = _FakeOpenFoodFactsService(error=ServiceError("nao encontrado", status_code=404))
    service = CaloriasTextoService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=openai_client,  # type: ignore[arg-type]
        taco_online_service=taco,  # type: ignore[arg-type]
        open_food_facts_service=off,  # type: ignore[arg-type]
    )

    result = service.calcular(texto="120 g de arroz; 80 g de feijao")

    assert len(result.itens) == 2
    assert result.totais.calorias_kcal == 220.0
    assert taco.calls == []
    assert off.calls == []
    assert len(openai_client.calls) == 1

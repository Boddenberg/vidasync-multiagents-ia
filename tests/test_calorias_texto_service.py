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
    def __init__(
        self,
        *,
        response: TacoOnlineFoodResponse | None = None,
        responses_by_query: dict[str, TacoOnlineFoodResponse] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._response = response
        self._responses_by_query = responses_by_query or {}
        self._error = error
        self.calls: list[tuple[str, float]] = []

    def get_food(self, *, query: str | None = None, grams: float = 100.0, **_: object) -> TacoOnlineFoodResponse:
        self.calls.append((query or "", grams))
        if self._error is not None:
            raise self._error
        if query is not None and query in self._responses_by_query:
            return self._responses_by_query[query]
        assert self._response is not None
        return self._response


class _FakeOpenFoodFactsService:
    def __init__(
        self,
        *,
        response: OpenFoodFactsSearchResponse | None = None,
        responses_by_query: dict[str, OpenFoodFactsSearchResponse] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._response = response
        self._responses_by_query = responses_by_query or {}
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
        if query in self._responses_by_query:
            return self._responses_by_query[query]
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


def _build_taco_response_from_per_100g(
    *,
    grams: float,
    energy_kcal_100g: float,
    adjusted_energy_kcal: float,
    nome_alimento: str = "Arroz cozido",
    slug: str = "arroz",
    grupo_alimentar: str = "Cereais",
    protein_g_100g: float = 2.5,
    carbs_g_100g: float = 28.0,
    fat_g_100g: float = 0.3,
) -> TacoOnlineFoodResponse:
    return TacoOnlineFoodResponse(
        url_pagina=f"https://www.tabelatacoonline.com.br/tabela-nutricional/taco/{slug}",
        slug=slug,
        gramas=grams,
        nome_alimento=nome_alimento,
        grupo_alimentar=grupo_alimentar,
        base_calculo="100 gramas",
        por_100g=TacoOnlineNutrients(
            energia_kcal=energy_kcal_100g,
            proteina_g=protein_g_100g,
            carboidratos_g=carbs_g_100g,
            lipidios_g=fat_g_100g,
        ),
        ajustado=TacoOnlineNutrients(
            energia_kcal=adjusted_energy_kcal,
            proteina_g=1.0,
            carboidratos_g=1.0,
            lipidios_g=1.0,
        ),
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


def _build_off_response_with_products(
    *,
    query: str,
    grams: float,
    products: list[OpenFoodFactsProduct],
) -> OpenFoodFactsSearchResponse:
    return OpenFoodFactsSearchResponse(
        consulta=query,
        gramas=grams,
        page=1,
        page_size=5,
        total_produtos=len(products),
        produtos=products,
        extraido_em=datetime.now(timezone.utc),
    )


def test_calorias_texto_service_usa_fontes_em_paralelo_e_seletor() -> None:
    query = "bebida energetica"
    grams = 500.0
    openai_client = _FakeOpenAIClient(
        selector_payload={
            "pode_responder": True,
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
    assert result.selecao_fonte.pode_responder is True
    assert result.selecao_fonte.fonte_escolhida == "OPEN_FOOD_FACTS"
    assert result.itens[0].calorias_kcal == 225.0
    assert result.totais.calorias_kcal == 225.0
    assert len(openai_client.calls) == 1


def test_calorias_texto_service_calcula_proporcionalmente_quando_llm_indica_que_pode_responder() -> None:
    grams = 135.0
    openai_client = _FakeOpenAIClient(
        selector_payload={
            "pode_responder": True,
            "fonte_escolhida": "TABELA_TACO_ONLINE",
            "confianca": 0.93,
            "justificativa": "Ha dados estruturados suficientes para calcular proporcionalmente.",
        }
    )
    service = CaloriasTextoService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=openai_client,  # type: ignore[arg-type]
        taco_online_service=_FakeTacoService(
            response=_build_taco_response_from_per_100g(
                grams=grams,
                energy_kcal_100g=128.0,
                adjusted_energy_kcal=999.0,
                protein_g_100g=2.5,
                carbs_g_100g=28.0,
                fat_g_100g=0.3,
            )
        ),  # type: ignore[arg-type]
        open_food_facts_service=_FakeOpenFoodFactsService(
            error=ServiceError("nao encontrado", status_code=404)
        ),  # type: ignore[arg-type]
    )

    result = service.calcular(texto="135 g de arroz")

    assert result.selecao_fonte is not None
    assert result.selecao_fonte.pode_responder is True
    assert result.selecao_fonte.fonte_escolhida == "TABELA_TACO_ONLINE"
    assert result.itens[0].alimento == "Arroz cozido"
    assert result.itens[0].calorias_kcal == 172.8
    assert result.itens[0].proteina_g == 3.375
    assert result.itens[0].carboidratos_g == 37.8
    assert result.itens[0].lipidios_g == 0.405
    assert result.totais.calorias_kcal == 172.8
    assert len(openai_client.calls) == 1


def test_calorias_texto_service_mantem_fluxo_atual_quando_llm_indica_que_nao_pode_responder() -> None:
    llm_payload = {
        "itens": [
            {
                "descricao_original": "200 g de comida nada a ver",
                "alimento": "comida nada a ver",
                "quantidade_texto": "200 g",
                "calorias_kcal": 210.0,
                "proteina_g": 8.0,
                "carboidratos_g": 25.0,
                "lipidios_g": 9.0,
                "confianca": 0.41,
                "observacoes": "Estimativa inferida pela LLM.",
            }
        ],
        "totais": {
            "calorias_kcal": 210.0,
            "proteina_g": 8.0,
            "carboidratos_g": 25.0,
            "lipidios_g": 9.0,
        },
        "warnings": ["Base estruturada insuficiente; aplicado fallback com inferencia."],
    }
    openai_client = _FakeOpenAIClient(
        selector_payload={
            "pode_responder": False,
            "confianca": 0.22,
            "justificativa": "Os candidatos estruturados nao parecem corresponder ao item pedido.",
        },
        llm_payload=llm_payload,
    )
    service = CaloriasTextoService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=openai_client,  # type: ignore[arg-type]
        taco_online_service=_FakeTacoService(
            response=_build_taco_response_from_per_100g(
                grams=200.0,
                energy_kcal_100g=128.0,
                adjusted_energy_kcal=256.0,
            )
        ),  # type: ignore[arg-type]
        open_food_facts_service=_FakeOpenFoodFactsService(
            response=_build_off_response(query="comida nada a ver", grams=200.0, energy_kcal=400.0)
        ),  # type: ignore[arg-type]
    )

    result = service.calcular(texto="200 g de comida nada a ver")

    assert result.selecao_fonte is None
    assert result.fontes_consultadas == []
    assert result.itens[0].alimento == "comida nada a ver"
    assert result.totais.calorias_kcal == 210.0
    assert result.warnings == ["Base estruturada insuficiente; aplicado fallback com inferencia."]
    assert len(openai_client.calls) == 2


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


def test_calorias_texto_service_trata_lista_estruturada_item_a_item_e_soma_totais() -> None:
    openai_client = _FakeOpenAIClient(
        selector_payload={
            "itens": [
                {
                    "indice": 0,
                    "pode_responder": True,
                    "fonte_escolhida": "TABELA_TACO_ONLINE",
                    "confianca": 0.93,
                    "justificativa": "Arroz com base suficiente para calculo.",
                },
                {
                    "indice": 1,
                    "pode_responder": True,
                    "fonte_escolhida": "TABELA_TACO_ONLINE",
                    "confianca": 0.91,
                    "justificativa": "Feijao com base suficiente para calculo.",
                },
            ]
        }
    )
    taco = _FakeTacoService(
        responses_by_query={
            "arroz": _build_taco_response_from_per_100g(
                grams=120.0,
                energy_kcal_100g=128.0,
                adjusted_energy_kcal=153.6,
                nome_alimento="Arroz cozido",
                slug="arroz",
                protein_g_100g=2.5,
                carbs_g_100g=28.0,
                fat_g_100g=0.3,
            ),
            "feijao": _build_taco_response_from_per_100g(
                grams=80.0,
                energy_kcal_100g=76.0,
                adjusted_energy_kcal=60.8,
                nome_alimento="Feijao cozido",
                slug="feijao",
                protein_g_100g=4.8,
                carbs_g_100g=13.6,
                fat_g_100g=0.5,
            ),
        }
    )
    off = _FakeOpenFoodFactsService(error=ServiceError("nao encontrado", status_code=404))
    service = CaloriasTextoService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=openai_client,  # type: ignore[arg-type]
        taco_online_service=taco,  # type: ignore[arg-type]
        open_food_facts_service=off,  # type: ignore[arg-type]
    )

    result = service.calcular(texto="120 g de arroz; 80 g de feijao")

    assert len(result.itens) == 2
    assert result.selecao_fonte is None
    assert len(result.selecoes_fontes) == 2
    assert result.totais.calorias_kcal == 214.4
    assert result.totais.proteina_g == 6.84
    assert result.totais.carboidratos_g == 44.48
    assert result.totais.lipidios_g == 0.76
    assert taco.calls == [("arroz", 120.0), ("feijao", 80.0)]
    assert off.calls == [("arroz", 120.0), ("feijao", 80.0)]
    assert len(openai_client.calls) == 1


def test_calorias_texto_service_faz_fallback_para_fluxo_atual_quando_lista_tem_item_sem_resposta_confiavel() -> None:
    llm_payload = {
        "itens": [
            {"alimento": "arroz", "calorias_kcal": 150.0},
            {"alimento": "feijao", "calorias_kcal": 70.0},
        ],
        "totais": {"calorias_kcal": 220.0},
        "warnings": ["Lista caiu no fluxo atual por falta de confianca em um dos itens."],
    }
    openai_client = _FakeOpenAIClient(
        selector_payload={
            "itens": [
                {
                    "indice": 0,
                    "pode_responder": True,
                    "fonte_escolhida": "TABELA_TACO_ONLINE",
                },
                {
                    "indice": 1,
                    "pode_responder": False,
                    "justificativa": "Item com base incoerente.",
                },
            ]
        },
        llm_payload=llm_payload,
    )
    taco = _FakeTacoService(
        responses_by_query={
            "arroz": _build_taco_response_from_per_100g(
                grams=120.0,
                energy_kcal_100g=128.0,
                adjusted_energy_kcal=153.6,
                nome_alimento="Arroz cozido",
                slug="arroz",
            ),
            "feijao": _build_taco_response_from_per_100g(
                grams=80.0,
                energy_kcal_100g=76.0,
                adjusted_energy_kcal=60.8,
                nome_alimento="Feijao cozido",
                slug="feijao",
            ),
        }
    )
    off = _FakeOpenFoodFactsService(error=ServiceError("nao encontrado", status_code=404))
    service = CaloriasTextoService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=openai_client,  # type: ignore[arg-type]
        taco_online_service=taco,  # type: ignore[arg-type]
        open_food_facts_service=off,  # type: ignore[arg-type]
    )

    result = service.calcular(texto="120 g de arroz; 80 g de feijao")

    assert result.selecao_fonte is None
    assert result.selecoes_fontes == []
    assert result.totais.calorias_kcal == 220.0
    assert result.warnings == ["Lista caiu no fluxo atual por falta de confianca em um dos itens."]
    assert taco.calls == [("arroz", 120.0), ("feijao", 80.0)]
    assert off.calls == [("arroz", 120.0), ("feijao", 80.0)]
    assert len(openai_client.calls) == 2


def test_calorias_texto_service_off_prioriza_produto_aderente_ao_nome() -> None:
    query = "monster energy ultra"
    grams = 473.0
    off_products = [
        OpenFoodFactsProduct(
            codigo_barras="0001",
            nome_produto="Snack de amendoim",
            marcas="NAKD",
            por_100g=OpenFoodFactsNutrients(
                energia_kcal=520.0,
                proteina_g=12.0,
                carboidratos_g=30.0,
                lipidios_g=35.0,
            ),
            ajustado=OpenFoodFactsNutrients(
                energia_kcal=2459.6,
                proteina_g=56.76,
                carboidratos_g=141.9,
                lipidios_g=165.55,
            ),
        ),
        OpenFoodFactsProduct(
            codigo_barras="0002",
            nome_produto="Monster Energy Ultra",
            marcas="Monster Energy",
            por_100g=OpenFoodFactsNutrients(
                energia_kcal=42.0,
                proteina_g=0.0,
                carboidratos_g=10.0,
                lipidios_g=0.0,
            ),
            ajustado=OpenFoodFactsNutrients(
                energia_kcal=198.66,
                proteina_g=0.0,
                carboidratos_g=47.3,
                lipidios_g=0.0,
            ),
        ),
    ]
    service = CaloriasTextoService(
        settings=Settings(openai_api_key="test-key", openai_model="gpt-4o-mini"),
        client=_FakeOpenAIClient(),  # type: ignore[arg-type]
        taco_online_service=_FakeTacoService(error=ServiceError("nao encontrado", status_code=404)),  # type: ignore[arg-type]
        open_food_facts_service=_FakeOpenFoodFactsService(  # type: ignore[arg-type]
            response=_build_off_response_with_products(query=query, grams=grams, products=off_products)
        ),
    )

    result = service.calcular(texto="473 g de Monster Energy Ultra")

    assert result.itens[0].alimento == "Monster Energy Ultra"
    assert result.totais.calorias_kcal == 198.66
    assert result.fontes_consultadas[0].item == "Monster Energy Ultra"

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_open_food_facts_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import (
    OpenFoodFactsNutrients,
    OpenFoodFactsProduct,
    OpenFoodFactsSearchResponse,
)


class _FakeOpenFoodFactsService:
    def search(
        self,
        *,
        query: str,
        grams: float = 100.0,
        page: int = 1,
        page_size: int = 10,
    ) -> OpenFoodFactsSearchResponse:
        return OpenFoodFactsSearchResponse(
            consulta=query,
            gramas=grams,
            page=page,
            page_size=page_size,
            total_produtos=1,
            produtos=[
                OpenFoodFactsProduct(
                    codigo_barras="5060337500401",
                    nome_produto="Monster Energy Ultra",
                    marcas="Monster Energy",
                    url_imagem="https://example.com/monster.jpg",
                    por_100g=OpenFoodFactsNutrients(energia_kcal=42.0, carboidratos_g=10.0),
                    ajustado=OpenFoodFactsNutrients(energia_kcal=210.0, carboidratos_g=50.0),
                )
            ],
            extraido_em=datetime(2026, 3, 8, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_open_food_facts_search_route_returns_payload() -> None:
    app.dependency_overrides[get_open_food_facts_service] = lambda: _FakeOpenFoodFactsService()
    client = TestClient(app)

    try:
        response = client.post(
            "/open-food-facts/search",
            json={"consulta": "monster energy ultra", "gramas": 500, "page": 1, "page_size": 5},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["fonte"] == "OPEN_FOOD_FACTS"
        assert body["consulta"] == "monster energy ultra"
        assert body["gramas"] == 500.0
        assert body["total_produtos"] == 1
        assert body["produtos"][0]["codigo_barras"] == "5060337500401"
        assert body["produtos"][0]["ajustado"]["energia_kcal"] == 210.0
    finally:
        app.dependency_overrides.clear()

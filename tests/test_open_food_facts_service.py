from vidasync_multiagents_ia.schemas import OpenFoodFactsSearchResponse
from vidasync_multiagents_ia.services.open_food_facts_service import OpenFoodFactsService


class _FakeOpenFoodFactsClient:
    def search_products(self, *, query: str, page: int = 1, page_size: int = 10) -> dict:
        assert query == "monster energy ultra"
        assert page == 1
        assert page_size == 5
        return {
            "count": 2,
            "products": [
                {
                    "code": "5060337500401",
                    "product_name": "Monster Energy Ultra",
                    "brands": "Monster Energy",
                    "image_url": "https://example.com/monster.jpg",
                    "nutriments": {
                        "energy-kcal_100g": 42,
                        "energy-kj_100g": 176,
                        "proteins_100g": 0.0,
                        "carbohydrates_100g": 10.0,
                        "fat_100g": 0.0,
                        "sugars_100g": 10.0,
                    },
                },
                {
                    "code": "1234567890",
                    "product_name": "Energy Zero",
                    "brands": "Brand X",
                    "nutriments": {
                        "energy-kcal_100g": 1.0,
                        "carbohydrates_100g": 0.0,
                    },
                },
            ],
        }


def test_open_food_facts_service_search_scales_nutrients() -> None:
    service = OpenFoodFactsService(client=_FakeOpenFoodFactsClient())  # type: ignore[arg-type]

    result: OpenFoodFactsSearchResponse = service.search(
        query="monster energy ultra",
        grams=500.0,
        page=1,
        page_size=5,
    )

    assert result.total_produtos == 2
    assert len(result.produtos) == 2
    assert result.produtos[0].codigo_barras == "5060337500401"
    assert result.produtos[0].por_100g.energia_kcal == 42.0
    assert result.produtos[0].ajustado.energia_kcal == 210.0
    assert result.produtos[0].ajustado.carboidratos_g == 50.0

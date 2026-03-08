from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_taco_online_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import TacoOnlineFoodResponse, TacoOnlineNutrients


class _FakeTacoOnlineService:
    def get_food(
        self,
        *,
        slug: str | None = None,
        page_url: str | None = None,
        query: str | None = None,
        grams: float = 100.0,
    ) -> TacoOnlineFoodResponse:
        return TacoOnlineFoodResponse(
            url_pagina=page_url
            or "https://www.tabelatacoonline.com.br/tabela-nutricional/taco/feijao-carioca-cru",
            slug=slug or "feijao-carioca-cru",
            gramas=grams,
            nome_alimento="Feijao, carioca, cru",
            grupo_alimentar="Leguminosas e derivados",
            base_calculo="100 gramas",
            por_100g=TacoOnlineNutrients(
                energia_kcal=329.0,
                proteina_g=20.0,
                carboidratos_g=61.2,
                lipidios_g=1.3,
            ),
            ajustado=TacoOnlineNutrients(
                energia_kcal=493.5,
                proteina_g=30.0,
                carboidratos_g=91.8,
                lipidios_g=1.95,
            ),
            extraido_em=datetime(2026, 3, 6, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_taco_online_food_endpoint_returns_payload() -> None:
    app.dependency_overrides[get_taco_online_service] = lambda: _FakeTacoOnlineService()
    client = TestClient(app)

    try:
        response = client.post(
            "/taco-online/food",
            json={"consulta": "feijao", "gramas": 150},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["contexto"] == "consultar_taco_online"
        assert body["fonte"] == "TABELA_TACO_ONLINE"
        assert body["slug"] == "feijao-carioca-cru"
        assert body["gramas"] == 150.0
        assert body["por_100g"]["energia_kcal"] == 329.0
    finally:
        app.dependency_overrides.clear()


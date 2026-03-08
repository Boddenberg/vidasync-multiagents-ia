from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_tbca_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import TBCAFoodSelection, TBCAMacros, TBCASearchResponse


class _FakeTBCAService:
    def search(self, query: str, grams: float = 100.0) -> TBCASearchResponse:
        return TBCASearchResponse(
            consulta=query,
            gramas=grams,
            alimento_selecionado=TBCAFoodSelection(
                codigo="BRC0001A",
                nome="Arroz teste",
                url_detalhe="https://www.tbca.net.br/base-dados/int_composicao_alimentos.php?fake",
            ),
            por_100g=TBCAMacros(
                energia_kcal=100.0,
                proteina_g=2.0,
                carboidratos_g=20.0,
                lipidios_g=1.0,
            ),
            ajustado=TBCAMacros(
                energia_kcal=150.0,
                proteina_g=3.0,
                carboidratos_g=30.0,
                lipidios_g=1.5,
            ),
        )


def test_tbca_search_post_with_body() -> None:
    app.dependency_overrides[get_tbca_service] = lambda: _FakeTBCAService()
    client = TestClient(app)

    try:
        response = client.post(
            "/tbca/search",
            json={"consulta": "arroz", "gramas": 150},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["contexto"] == "consultar_tbca"
        assert payload["consulta"] == "arroz"
        assert payload["gramas"] == 150.0
        assert payload["alimento_selecionado"]["codigo"] == "BRC0001A"
    finally:
        app.dependency_overrides.clear()

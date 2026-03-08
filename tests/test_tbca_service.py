import pytest

from vidasync_multiagents_ia.schemas import TBCAFoodCandidate, TBCANutrientRow
from vidasync_multiagents_ia.services.tbca_service import TBCAService


class _FakeTBCAClient:
    def search_foods(self, query: str) -> list[TBCAFoodCandidate]:
        assert query == "arroz branco cozido"
        return [
            TBCAFoodCandidate(
                code="BRC0016A",
                name="Arroz integral, cozido, s/ sal, s/ oleo",
                detail_path="int_composicao_alimentos.php?token=integral",
            ),
            TBCAFoodCandidate(
                code="BRC0018A",
                name="Arroz branco cozido, s/ oleo, s/ sal",
                detail_path="int_composicao_alimentos.php?token=branco",
            ),
        ]

    def fetch_food_nutrients(self, detail_path: str) -> tuple[str, list[TBCANutrientRow]]:
        assert detail_path == "int_composicao_alimentos.php?token=branco"
        return (
            "https://www.tbca.net.br/base-dados/int_composicao_alimentos.php?token=branco",
            [
                TBCANutrientRow(component="Energia", unit="kJ", value_per_100g="401"),
                TBCANutrientRow(component="Energia", unit="kcal", value_per_100g="96"),
                TBCANutrientRow(component="Carboidrato total", unit="g", value_per_100g="21,9"),
                TBCANutrientRow(component="Proteina", unit="g", value_per_100g="2,01"),
                TBCANutrientRow(component="Lipidios", unit="g", value_per_100g="0,14"),
            ],
        )


class _FakeTBCAClientWithMissingNutrients:
    def search_foods(self, query: str) -> list[TBCAFoodCandidate]:
        return [
            TBCAFoodCandidate(
                code="BRC9999A",
                name="Arroz teste",
                detail_path="int_composicao_alimentos.php?token=teste",
            )
        ]

    def fetch_food_nutrients(self, detail_path: str) -> tuple[str, list[TBCANutrientRow]]:
        return (
            "https://www.tbca.net.br/base-dados/int_composicao_alimentos.php?token=teste",
            [
                TBCANutrientRow(component="Energia", unit="kcal", value_per_100g="128,34"),
                TBCANutrientRow(component="Carboidrato total", unit="g", value_per_100g="31,00"),
            ],
        )


def test_tbca_service_selects_best_candidate_and_adjusts_grams() -> None:
    service = TBCAService(client=_FakeTBCAClient())  # type: ignore[arg-type]

    result = service.search(query="arroz branco cozido", grams=150)

    assert result.alimento_selecionado.codigo == "BRC0018A"
    assert result.alimento_selecionado.nome == "Arroz branco cozido, s/ oleo, s/ sal"
    assert result.por_100g.energia_kcal == 96.0
    assert result.por_100g.proteina_g == pytest.approx(2.01)
    assert result.por_100g.carboidratos_g == pytest.approx(21.9)
    assert result.por_100g.lipidios_g == pytest.approx(0.14)
    assert result.ajustado.energia_kcal == 144.0
    assert result.ajustado.proteina_g == pytest.approx(3.015)
    assert result.ajustado.carboidratos_g == pytest.approx(32.85)
    assert result.ajustado.lipidios_g == pytest.approx(0.21)


def test_tbca_service_keeps_missing_nutrients_as_null() -> None:
    service = TBCAService(client=_FakeTBCAClientWithMissingNutrients())  # type: ignore[arg-type]

    result = service.search(query="arroz", grams=200)

    assert result.por_100g.energia_kcal == pytest.approx(128.34)
    assert result.por_100g.carboidratos_g == pytest.approx(31.0)
    assert result.por_100g.proteina_g is None
    assert result.por_100g.lipidios_g is None
    assert result.ajustado.energia_kcal == pytest.approx(256.68)
    assert result.ajustado.carboidratos_g == pytest.approx(62.0)
    assert result.ajustado.proteina_g is None
    assert result.ajustado.lipidios_g is None

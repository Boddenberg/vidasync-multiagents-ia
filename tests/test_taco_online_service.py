from vidasync_multiagents_ia.clients.taco_online_client import TacoOnlineClient
from vidasync_multiagents_ia.schemas import TacoOnlineFoodIndexItem, TacoOnlineRawFoodData
from vidasync_multiagents_ia.services.taco_online_service import TacoOnlineService, _parse_brazilian_number


def test_taco_online_parser_extracts_public_fields_from_html() -> None:
    html_mock = """
    <html>
      <body>
        <script>
          self.__next_f.push([1,"7:[\\"$\\",{\\"data\\":{\\"id\\":562,\\"grupo\\":\\"Leguminosas e derivados\\",\\"descricao\\":\\"Feijao, carioca, cru\\",\\"slug\\":\\"feijao-carioca-cru\\",\\"umidade\\":\\"14,0\\",\\"energia_kcal\\":329,\\"energia_kj\\":1377,\\"proteina_g\\":\\"20,0\\",\\"lipideos_g\\":\\"1,3\\",\\"carboidrato_g\\":\\"61,2\\",\\"fibra_alimentar_g\\":\\"18,4\\",\\"cinzas_g\\":\\"3,5\\",\\"calcio_mg\\":123,\\"magnesio_mg\\":210,\\"manganes_mg\\":\\"1,02\\",\\"fosforo_mg\\":385,\\"ferro_mg\\":\\"8,0\\",\\"sodio_mg\\":\\"Tr\\",\\"potassio_mg\\":1352,\\"cobre_mg\\":\\"0,79\\",\\"zinco_mg\\":\\"2,9\\",\\"retinol_ug\\":\\"NA\\",\\"tiamina_mg\\":\\"0,17\\",\\"riboflavina_mg\\":\\"Tr\\",\\"piridoxina_mg\\":\\"0,65\\",\\"niacina_mg\\":\\"4,02\\"}}"]);
        </script>
        <script>
          self.__next_f.push([1,"\\"servingSize\\":\\"100g\\""]);
        </script>
      </body>
    </html>
    """

    client = TacoOnlineClient()
    raw_data = client.extract_public_food_data(html=html_mock, expected_slug="feijao-carioca-cru")

    assert raw_data.slug == "feijao-carioca-cru"
    assert raw_data.nome_alimento == "Feijao, carioca, cru"
    assert raw_data.grupo_alimentar == "Leguminosas e derivados"
    assert raw_data.base_calculo == "100 gramas"
    assert raw_data.nutrientes["energia_kcal"] == "329"
    assert raw_data.nutrientes["carboidratos_g"] == "61,2"
    assert raw_data.nutrientes["sodio_mg"] == "Tr"
    assert raw_data.nutrientes["retinol_mcg"] == "NA"


def test_parse_brazilian_number_handles_units_and_special_values() -> None:
    assert _parse_brazilian_number("61,20 g") == 61.2
    assert _parse_brazilian_number("1,30 g") == 1.3
    assert _parse_brazilian_number("329 kcal") == 329.0
    assert _parse_brazilian_number("14 %") == 14.0
    assert _parse_brazilian_number("1.352,0 mg") == 1352.0
    assert _parse_brazilian_number("Tr") is None
    assert _parse_brazilian_number("NA") is None
    assert _parse_brazilian_number("") is None


class _FakeClientQueryResolution:
    def find_best_taco_slug(self, query: str) -> TacoOnlineFoodIndexItem | None:
        assert query == "feijao"
        return TacoOnlineFoodIndexItem(
            slug="feijao-carioca-cru",
            nome_alimento="Feijao, carioca, cru",
            grupo_alimentar="Leguminosas e derivados",
            tabela="TACO",
        )

    def fetch_html(self, page_url: str) -> str:
        assert page_url.endswith("/tabela-nutricional/taco/feijao-carioca-cru")
        return "<html/>"

    def extract_public_food_data(self, html: str, expected_slug: str | None) -> TacoOnlineRawFoodData:
        assert expected_slug == "feijao-carioca-cru"
        return TacoOnlineRawFoodData(
            slug="feijao-carioca-cru",
            nome_alimento="Feijao, carioca, cru",
            grupo_alimentar="Leguminosas e derivados",
            base_calculo="100 gramas",
            nutrientes={
                "energia_kcal": "329",
                "energia_kj": "1377",
                "carboidratos_g": "61,2",
                "proteina_g": "20,0",
                "lipidios_g": "1,3",
            },
        )


def test_taco_online_service_resolves_slug_from_query() -> None:
    service = TacoOnlineService(client=_FakeClientQueryResolution())  # type: ignore[arg-type]
    result = service.get_food(query="feijao", grams=150)

    assert result.slug == "feijao-carioca-cru"
    assert result.nome_alimento == "Feijao, carioca, cru"
    assert result.por_100g.energia_kcal == 329.0
    assert result.ajustado.energia_kcal == 493.5


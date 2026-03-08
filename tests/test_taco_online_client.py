from vidasync_multiagents_ia.clients.taco_online_client import TacoOnlineClient


def test_taco_online_client_extracts_public_index_items() -> None:
    html = """
    \\\"slug\\\":\\\"feijao-carioca-cru\\\",\\\"descricao\\\":\\\"Feijao, carioca, cru\\\",\\\"grupo_slug\\\":\\\"leguminosas\\\",\\\"table\\\":\\\"TACO\\\",\\\"grupo\\\":\\\"Leguminosas e derivados\\\"
    \\\"slug\\\":\\\"arroz-branco-cozido\\\",\\\"descricao\\\":\\\"Arroz branco cozido\\\",\\\"grupo_slug\\\":\\\"cereais\\\",\\\"table\\\":\\\"IBGE\\\",\\\"grupo\\\":\\\"Cereais\\\"
    """

    client = TacoOnlineClient()
    items = client._extract_public_index_items(html)  # type: ignore[attr-defined]

    assert len(items) == 2
    assert items[0].slug == "feijao-carioca-cru"
    assert items[0].tabela == "TACO"
    assert items[1].slug == "arroz-branco-cozido"
    assert items[1].tabela == "IBGE"


def test_taco_online_client_extracts_public_food_data_window() -> None:
    html = """
    <script>
      var food = {
        \\"slug\\":\\"feijao-carioca-cru\\",
        \\"descricao\\":\\"Feijao, carioca, cru\\",
        \\"grupo\\":\\"Leguminosas e derivados\\",
        \\"servingSize\\":\\"100g\\",
        \\"energia_kcal\\":\\"329\\",
        \\"carboidrato_g\\":\\"61,20\\",
        \\"proteina_g\\":\\"20,0\\",
        \\"lipideos_g\\":\\"1,30\\"
      };
    </script>
    """

    client = TacoOnlineClient()
    food = client.extract_public_food_data(html=html, expected_slug="feijao-carioca-cru")

    assert food.slug == "feijao-carioca-cru"
    assert food.nome_alimento == "Feijao, carioca, cru"
    assert food.grupo_alimentar == "Leguminosas e derivados"
    assert food.base_calculo == "100 gramas"
    assert food.nutrientes["energia_kcal"] == "329"
    assert food.nutrientes["carboidratos_g"] == "61,20"
    assert food.nutrientes["proteina_g"] == "20,0"
    assert food.nutrientes["lipidios_g"] == "1,30"

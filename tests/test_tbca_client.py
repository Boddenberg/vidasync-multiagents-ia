from vidasync_multiagents_ia.clients.tbca_client import TBCAClient


def test_tbca_client_search_and_detail_parsing_with_mock_html() -> None:
    search_html = """
    <html>
      <body>
        <table>
          <tr>
            <td>BRC0018A</td>
            <td><a href="int_composicao_alimentos.php?token=abc123">Arroz branco cozido</a></td>
          </tr>
        </table>
      </body>
    </html>
    """
    detail_html = """
    <html>
      <body>
        <table id="tabela1">
          <tr><td>Componente</td><td>Unidade</td><td>100 g</td></tr>
          <tr><td>Energia</td><td>kcal</td><td>128,34</td></tr>
          <tr><td>Proteina</td><td>g</td><td>2,5</td></tr>
          <tr><td>Carboidrato total</td><td>g</td><td>28,1</td></tr>
          <tr><td>Lipidios</td><td>g</td><td>0,3</td></tr>
        </table>
      </body>
    </html>
    """

    client = TBCAClient()

    def _fake_request_html(url: str) -> str:
        if "int_composicao_alimentos.php" in url:
            return detail_html
        if "composicao_alimentos.php" in url:
            return search_html
        return ""

    client._request_html = _fake_request_html  # type: ignore[method-assign]

    foods = client.search_foods("arroz")
    assert len(foods) == 1
    assert foods[0].code == "BRC0018A"
    assert foods[0].name == "Arroz branco cozido"
    assert foods[0].detail_path == "int_composicao_alimentos.php?token=abc123"

    detail_url, rows = client.fetch_food_nutrients("int_composicao_alimentos.php?token=abc123")
    assert "int_composicao_alimentos.php?token=abc123" in detail_url
    assert len(rows) >= 4
    assert rows[0].component == "Energia"
    assert rows[0].unit == "kcal"
    assert rows[0].value_per_100g == "128,34"

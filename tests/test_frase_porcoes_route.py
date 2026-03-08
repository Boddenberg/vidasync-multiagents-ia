from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_frase_porcoes_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import (
    AgentePorcoesTexto,
    FrasePorcoesResponse,
    ItemPorcaoTexto,
    ResultadoPorcoesTexto,
)


class _FakeFrasePorcoesService:
    def extrair_porcoes(
        self,
        *,
        texto_transcrito: str,
        contexto: str = "interpretar_porcoes_texto",
        idioma: str = "pt-BR",
        inferir_quando_ausente: bool = False,
    ) -> FrasePorcoesResponse:
        assert inferir_quando_ausente is True
        return FrasePorcoesResponse(
            contexto=contexto,
            texto_transcrito=texto_transcrito,
            resultado_porcoes=ResultadoPorcoesTexto(
                itens=[
                    ItemPorcaoTexto(
                        nome_alimento="babaganuche",
                        consulta_canonica="babaganuche",
                        quantidade_original="50 gramas",
                        quantidade_gramas=50,
                        origem_quantidade="informada",
                        confianca=0.9,
                    ),
                ],
                observacoes_gerais="Parse baseado na frase.",
            ),
            agente=AgentePorcoesTexto(
                contexto="interpretar_porcoes_texto",
                nome_agente="agente_interpretacao_porcoes_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca_media=0.9,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_frase_porcoes_route_retorna_porcoes() -> None:
    app.dependency_overrides[get_frase_porcoes_service] = lambda: _FakeFrasePorcoesService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/texto/extrair-porcoes",
            json={
                "contexto": "interpretar_porcoes_texto",
                "texto_transcrito": "Comi 50 gramas de babaganuche.",
                "idioma": "pt-BR",
                "inferir_quando_ausente": True,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["contexto"] == "interpretar_porcoes_texto"
        assert body["resultado_porcoes"]["itens"][0]["nome_alimento"] == "babaganuche"
        assert body["agente"]["nome_agente"] == "agente_interpretacao_porcoes_texto"
    finally:
        app.dependency_overrides.clear()

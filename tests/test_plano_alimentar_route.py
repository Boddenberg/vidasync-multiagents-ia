from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_plano_alimentar_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import (
    AgenteEstruturacaoPlano,
    PlanoAlimentarEstruturado,
    PlanoAlimentarResponse,
)


class _FakePlanoAlimentarService:
    def estruturar_plano(
        self,
        *,
        textos_fonte: list[str],
        contexto: str = "estruturar_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoAlimentarResponse:
        assert textos_fonte == ["texto principal", "texto complementar"]
        return PlanoAlimentarResponse(
            contexto=contexto,
            idioma=idioma,
            fontes_processadas=len(textos_fonte),
            plano_alimentar=PlanoAlimentarEstruturado(
                tipo_plano="plano alimentar",
                objetivos=["reduzir gordura"],
            ),
            agente=AgenteEstruturacaoPlano(
                contexto="estruturar_plano_alimentar",
                nome_agente="agente_estrutura_plano_alimentar",
                status="sucesso",
                modelo="gpt-4o-mini",
                fontes_processadas=len(textos_fonte),
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_plano_alimentar_route_retorna_estrutura_do_plano() -> None:
    app.dependency_overrides[get_plano_alimentar_service] = lambda: _FakePlanoAlimentarService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/texto/estruturar-plano-alimentar",
            json={
                "contexto": "estruturar_plano_alimentar",
                "idioma": "pt-BR",
                "texto_transcrito": "texto principal",
                "textos_fonte": ["texto complementar", "texto principal"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["contexto"] == "estruturar_plano_alimentar"
        assert body["fontes_processadas"] == 2
        assert body["plano_alimentar"]["objetivos"] == ["reduzir gordura"]
        assert body["agente"]["nome_agente"] == "agente_estrutura_plano_alimentar"
    finally:
        app.dependency_overrides.clear()

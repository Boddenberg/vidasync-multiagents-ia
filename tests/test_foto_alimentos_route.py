from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_foto_alimentos_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import (
    EstimativaPorcoesFotoResponse,
    ExecucaoAgenteFoto,
    IdentificacaoFotoResponse,
    ItemAlimentoEstimado,
    ResultadoIdentificacaoFoto,
    ResultadoPorcoesFoto,
)


class _FakeFotoAlimentosService:
    def identificar_se_e_foto_de_comida(
        self,
        *,
        imagem_url: str,
        contexto: str = "identificar_fotos",
        idioma: str = "pt-BR",
    ) -> IdentificacaoFotoResponse:
        return IdentificacaoFotoResponse(
            contexto=contexto,
            imagem_url=imagem_url,
            resultado_identificacao=ResultadoIdentificacaoFoto(
                eh_comida=True,
                qualidade_adequada=True,
                motivo="Foto adequada.",
                confianca=0.91,
            ),
            agente=ExecucaoAgenteFoto(
                contexto="identificar_se_e_foto_de_comida",
                nome_agente="agente_portaria_comida",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca=0.91,
                saida={"eh_comida": True},
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )

    def estimar_porcoes_do_prato(
        self,
        *,
        imagem_url: str,
        contexto: str = "estimar_porcoes_do_prato",
        idioma: str = "pt-BR",
    ) -> EstimativaPorcoesFotoResponse:
        return EstimativaPorcoesFotoResponse(
            contexto=contexto,
            imagem_url=imagem_url,
            resultado_porcoes=ResultadoPorcoesFoto(
                itens=[
                    ItemAlimentoEstimado(
                        nome_alimento="Arroz branco cozido",
                        consulta_canonica="arroz branco cozido",
                        quantidade_estimada_gramas=120,
                        confianca=0.82,
                    )
                ],
                observacoes_gerais="Estimativa visual.",
            ),
            agente=ExecucaoAgenteFoto(
                contexto="estimar_porcoes_do_prato",
                nome_agente="agente_estimativa_porcoes",
                status="sucesso",
                modelo="gpt-4o-mini",
                confianca=0.82,
                saida={"itens": 1},
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_foto_alimentos_route_identificar_comida() -> None:
    app.dependency_overrides[get_foto_alimentos_service] = lambda: _FakeFotoAlimentosService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/fotos/identificar-comida",
            json={
                "contexto": "identificar_fotos",
                "imagem_url": "https://example.com/prato.jpg",
                "idioma": "pt-BR",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["contexto"] == "identificar_fotos"
        assert body["resultado_identificacao"]["eh_comida"] is True
        assert body["agente"]["nome_agente"] == "agente_portaria_comida"
    finally:
        app.dependency_overrides.clear()


def test_foto_alimentos_route_estimar_porcoes() -> None:
    app.dependency_overrides[get_foto_alimentos_service] = lambda: _FakeFotoAlimentosService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/fotos/estimar-porcoes",
            json={
                "contexto": "estimar_porcoes_do_prato",
                "imagem_url": "https://example.com/prato.jpg",
                "idioma": "pt-BR",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["contexto"] == "estimar_porcoes_do_prato"
        assert len(body["resultado_porcoes"]["itens"]) == 1
        assert body["agente"]["nome_agente"] == "agente_estimativa_porcoes"
    finally:
        app.dependency_overrides.clear()

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_imagem_texto_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import (
    AgenteTranscricaoImagemTexto,
    ImagemTextoItemResponse,
    ImagemTextoResponse,
)


class _FakeImagemTextoService:
    def transcrever_textos_de_imagens(
        self,
        *,
        imagem_urls: list[str],
        contexto: str = "transcrever_texto_imagem",
        idioma: str = "pt-BR",
    ) -> ImagemTextoResponse:
        return ImagemTextoResponse(
            contexto=contexto,
            idioma=idioma,
            total_imagens=len(imagem_urls),
            resultados=[
                ImagemTextoItemResponse(
                    imagem_url=imagem_urls[0],
                    status="sucesso",
                    texto_transcrito="SKU 1 - 4.90",
                )
            ],
            agente=AgenteTranscricaoImagemTexto(
                contexto="transcrever_texto_imagem",
                nome_agente="agente_ocr_imagem_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                modo_execucao="paralelo",
                total_imagens=len(imagem_urls),
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_imagem_texto_route_retorna_transcricao_em_lote() -> None:
    app.dependency_overrides[get_imagem_texto_service] = lambda: _FakeImagemTextoService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/imagens/transcrever-texto",
            json={
                "contexto": "transcrever_texto_imagem",
                "imagem_urls": [
                    "https://example.com/nota-fiscal.png",
                    "https://example.com/rotulo-produto.png",
                ],
                "idioma": "pt-BR",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["contexto"] == "transcrever_texto_imagem"
        assert body["total_imagens"] == 2
        assert body["resultados"][0]["texto_transcrito"] == "SKU 1 - 4.90"
        assert body["agente"]["nome_agente"] == "agente_ocr_imagem_texto"
    finally:
        app.dependency_overrides.clear()


def test_imagem_texto_route_aceita_imagem_url_unica() -> None:
    app.dependency_overrides[get_imagem_texto_service] = lambda: _FakeImagemTextoService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/imagens/transcrever-texto",
            json={
                "contexto": "transcrever_texto_imagem",
                "imagem_url": "https://example.com/nota-fiscal.png",
                "idioma": "pt-BR",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total_imagens"] == 1
        assert body["resultados"][0]["imagem_url"] == "https://example.com/nota-fiscal.png"
    finally:
        app.dependency_overrides.clear()

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_imagem_texto_service
from vidasync_multiagents_ia.main import app, settings
from vidasync_multiagents_ia.schemas import (
    AgenteTranscricaoImagemTexto,
    ImagemTextoItemResponse,
    ImagemTextoResponse,
)


class _FakeImagemTextoServiceComErroNulo:
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
                    texto_transcrito="texto extraido",
                    erro=None,
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


def test_response_exclude_none_false_mantem_campos_nulos() -> None:
    original_value = settings.response_exclude_none
    settings.response_exclude_none = False
    app.dependency_overrides[get_imagem_texto_service] = lambda: _FakeImagemTextoServiceComErroNulo()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/imagens/transcrever-texto",
            json={
                "contexto": "transcrever_texto_imagem",
                "imagem_url": "https://example.com/imagem.png",
                "idioma": "pt-BR",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "erro" in body["resultados"][0]
        assert body["resultados"][0]["erro"] is None
    finally:
        app.dependency_overrides.clear()
        settings.response_exclude_none = original_value


def test_response_exclude_none_true_remove_campos_nulos() -> None:
    original_value = settings.response_exclude_none
    settings.response_exclude_none = True
    app.dependency_overrides[get_imagem_texto_service] = lambda: _FakeImagemTextoServiceComErroNulo()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/imagens/transcrever-texto",
            json={
                "contexto": "transcrever_texto_imagem",
                "imagem_url": "https://example.com/imagem.png",
                "idioma": "pt-BR",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "erro" not in body["resultados"][0]
    finally:
        app.dependency_overrides.clear()
        settings.response_exclude_none = original_value

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_plano_texto_normalizado_service
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import (
    AgenteNormalizacaoPlanoTexto,
    PlanoTextoNormalizadoResponse,
    PlanoTextoNormalizadoSecao,
)


class _FakePlanoTextoNormalizadoService:
    def normalizar_de_imagens(
        self,
        *,
        imagem_urls: list[str],
        contexto: str = "normalizar_texto_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoTextoNormalizadoResponse:
        assert imagem_urls == ["https://example.com/plano.png"]
        return PlanoTextoNormalizadoResponse(
            contexto=contexto,
            idioma=idioma,
            tipo_fonte="imagem",
            total_fontes=1,
            titulo_documento="Plano Alimentar",
            secoes=[
                PlanoTextoNormalizadoSecao(
                    titulo="desjejum_07_00",
                    texto="QTD: 1 unidade | ALIMENTO: Ovo",
                )
            ],
            texto_normalizado="[desjejum_07_00]\nQTD: 1 unidade | ALIMENTO: Ovo",
            observacoes=[],
            agente=AgenteNormalizacaoPlanoTexto(
                contexto="normalizar_texto_plano_alimentar",
                nome_agente="agente_normalizacao_plano_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                tipo_fonte="imagem",
                total_fontes=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )

    def normalizar_de_pdf(
        self,
        *,
        pdf_bytes: bytes,
        nome_arquivo: str,
        contexto: str = "normalizar_texto_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoTextoNormalizadoResponse:
        assert pdf_bytes.startswith(b"%PDF-")
        assert nome_arquivo == "plano.pdf"
        return PlanoTextoNormalizadoResponse(
            contexto=contexto,
            idioma=idioma,
            tipo_fonte="pdf",
            total_fontes=1,
            titulo_documento="Plano Alimentar",
            secoes=[
                PlanoTextoNormalizadoSecao(
                    titulo="cabecalho",
                    texto="Paciente: Leticia",
                )
            ],
            texto_normalizado="[cabecalho]\nPaciente: Leticia",
            observacoes=[],
            agente=AgenteNormalizacaoPlanoTexto(
                contexto="normalizar_texto_plano_alimentar",
                nome_agente="agente_normalizacao_plano_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                tipo_fonte="pdf",
                total_fontes=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_plano_texto_normalizado_route_imagem() -> None:
    app.dependency_overrides[get_plano_texto_normalizado_service] = lambda: _FakePlanoTextoNormalizadoService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/documentos/normalizar-texto-imagens",
            json={
                "contexto": "normalizar_texto_plano_alimentar",
                "imagem_url": "https://example.com/plano.png",
                "idioma": "pt-BR",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tipo_fonte"] == "imagem"
        assert body["titulo_documento"] == "Plano Alimentar"
        assert body["secoes"][0]["titulo"] == "desjejum_07_00"
    finally:
        app.dependency_overrides.clear()


def test_plano_texto_normalizado_route_pdf() -> None:
    app.dependency_overrides[get_plano_texto_normalizado_service] = lambda: _FakePlanoTextoNormalizadoService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/documentos/normalizar-texto-pdf",
            data={"contexto": "normalizar_texto_plano_alimentar", "idioma": "pt-BR"},
            files={"pdf_file": ("plano.pdf", b"%PDF-1.7\nfake", "application/pdf")},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tipo_fonte"] == "pdf"
        assert body["titulo_documento"] == "Plano Alimentar"
        assert body["secoes"][0]["titulo"] == "cabecalho"
    finally:
        app.dependency_overrides.clear()

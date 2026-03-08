from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_pdf_texto_service
from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import AgenteTranscricaoPdf, PdfTextoResponse


class _FakePdfTextoService:
    def transcrever_pdf(
        self,
        *,
        pdf_bytes: bytes,
        nome_arquivo: str,
        contexto: str = "transcrever_texto_pdf",
        idioma: str = "pt-BR",
    ) -> PdfTextoResponse:
        assert pdf_bytes.startswith(b"%PDF-")
        return PdfTextoResponse(
            contexto=contexto,
            idioma=idioma,
            nome_arquivo=nome_arquivo,
            texto_transcrito="Texto do plano alimentar",
            agente=AgenteTranscricaoPdf(
                contexto="transcrever_texto_pdf",
                nome_agente="agente_transcricao_pdf",
                status="sucesso",
                modelo="gpt-4o-mini",
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_pdf_texto_route_transcreve_pdf_multipart() -> None:
    app.dependency_overrides[get_pdf_texto_service] = lambda: _FakePdfTextoService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/documentos/transcrever-pdf",
            data={"contexto": "transcrever_texto_pdf", "idioma": "pt-BR"},
            files={"pdf_file": ("plano.pdf", b"%PDF-1.7\nfake", "application/pdf")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["contexto"] == "transcrever_texto_pdf"
        assert body["nome_arquivo"] == "plano.pdf"
        assert body["texto_transcrito"] == "Texto do plano alimentar"
        assert body["agente"]["nome_agente"] == "agente_transcricao_pdf"
    finally:
        app.dependency_overrides.clear()


def test_pdf_texto_route_rejeita_arquivo_acima_do_limite() -> None:
    app.dependency_overrides[get_pdf_texto_service] = lambda: _FakePdfTextoService()
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="test-key",
        pdf_max_upload_bytes=4,
    )
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/documentos/transcrever-pdf",
            data={"contexto": "transcrever_texto_pdf", "idioma": "pt-BR"},
            files={"pdf_file": ("plano.pdf", b"%PDF-1.7\nfake", "application/pdf")},
        )
        assert response.status_code == 413
        assert "acima do limite" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()

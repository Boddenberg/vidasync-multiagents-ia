from datetime import datetime, timezone

from fastapi.testclient import TestClient

from vidasync_multiagents_ia.api.dependencies import get_audio_transcricao_service
from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.main import app
from vidasync_multiagents_ia.schemas import AgenteTranscricaoAudio, AudioTranscricaoResponse


class _FakeAudioTranscricaoService:
    def transcrever_audio(
        self,
        *,
        audio_bytes: bytes,
        nome_arquivo: str,
        contexto: str = "transcrever_audio_usuario",
        idioma: str = "pt-BR",
    ) -> AudioTranscricaoResponse:
        assert audio_bytes == b"audio-bytes"
        return AudioTranscricaoResponse(
            contexto=contexto,
            idioma=idioma,
            nome_arquivo=nome_arquivo,
            texto_transcrito="comi frango e salada",
            agente=AgenteTranscricaoAudio(
                contexto="transcrever_audio_usuario",
                nome_agente="agente_transcricao_audio",
                status="sucesso",
                modelo="gpt-4o-mini-transcribe",
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_audio_transcricao_route_multipart() -> None:
    app.dependency_overrides[get_audio_transcricao_service] = lambda: _FakeAudioTranscricaoService()
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/audio/transcrever",
            data={"contexto": "transcrever_audio_usuario", "idioma": "pt-BR"},
            files={"audio_file": ("audio_teste.webm", b"audio-bytes", "audio/webm")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["contexto"] == "transcrever_audio_usuario"
        assert body["idioma"] == "pt-BR"
        assert body["nome_arquivo"] == "audio_teste.webm"
        assert body["texto_transcrito"] == "comi frango e salada"
        assert body["agente"]["nome_agente"] == "agente_transcricao_audio"
    finally:
        app.dependency_overrides.clear()


def test_audio_transcricao_route_rejects_large_payload() -> None:
    app.dependency_overrides[get_audio_transcricao_service] = lambda: _FakeAudioTranscricaoService()
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="test-key",
        audio_max_upload_bytes=4,
    )
    client = TestClient(app)

    try:
        response = client.post(
            "/agentes/audio/transcrever",
            data={"contexto": "transcrever_audio_usuario", "idioma": "pt-BR"},
            files={"audio_file": ("audio_teste.webm", b"audio-bytes", "audio/webm")},
        )
        assert response.status_code == 413
        assert "acima do limite" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()

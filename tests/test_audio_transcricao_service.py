from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.services.audio_transcricao_service import AudioTranscricaoService


class _FakeOpenAIClient:
    def transcribe_audio(
        self,
        *,
        model: str,
        audio_bytes: bytes,
        filename: str,
        language: str | None = None,
    ) -> str:
        assert model == "gpt-4o-mini-transcribe"
        assert filename == "audio_teste.webm"
        assert language == "pt"
        assert audio_bytes == b"audio-bytes"
        return "comi arroz e feijao no almoco"


def test_audio_transcricao_service_transcreve_audio() -> None:
    settings = Settings(openai_api_key="test-key", openai_audio_model="gpt-4o-mini-transcribe")
    service = AudioTranscricaoService(settings=settings, client=_FakeOpenAIClient())  # type: ignore[arg-type]

    result = service.transcrever_audio(
        audio_bytes=b"audio-bytes",
        nome_arquivo="audio_teste.webm",
        contexto="transcrever_audio_usuario",
        idioma="pt-BR",
    )

    assert result.contexto == "transcrever_audio_usuario"
    assert result.texto_transcrito == "comi arroz e feijao no almoco"
    assert result.agente.nome_agente == "agente_transcricao_audio"
    assert result.agente.modelo == "gpt-4o-mini-transcribe"

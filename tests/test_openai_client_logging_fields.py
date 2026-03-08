from types import SimpleNamespace

from vidasync_multiagents_ia.clients.openai_client import OpenAIClient


class _FakeFiles:
    def create(self, *, file, purpose: str):  # type: ignore[no-untyped-def]
        assert purpose == "user_data"
        assert file[0] == "documento.pdf"
        return SimpleNamespace(id="file_123")

    def delete(self, file_id: str) -> None:
        assert file_id == "file_123"


class _FakeResponses:
    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["model"] == "gpt-4o-mini"
        return SimpleNamespace(output_text="texto extraido do pdf")


class _FakeAudioTranscriptions:
    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        assert kwargs["model"] == "gpt-4o-mini-transcribe"
        return SimpleNamespace(text="texto transcrito de audio")


class _FakeAudio:
    def __init__(self) -> None:
        self.transcriptions = _FakeAudioTranscriptions()


class _FakeOpenAISdkForPdf:
    def __init__(self) -> None:
        self.files = _FakeFiles()
        self.responses = _FakeResponses()


class _FakeOpenAISdkForAudio:
    def __init__(self) -> None:
        self.audio = _FakeAudio()


def test_openai_client_extract_text_from_pdf_sem_colisao_de_logrecord() -> None:
    client = OpenAIClient(api_key="test-key", timeout_seconds=5)
    client._client = _FakeOpenAISdkForPdf()  # type: ignore[assignment]

    result = client.extract_text_from_pdf(
        model="gpt-4o-mini",
        system_prompt="sistema",
        user_prompt="usuario",
        pdf_bytes=b"%PDF-1.7\nfake",
        filename="documento.pdf",
    )

    assert result == "texto extraido do pdf"


def test_openai_client_transcribe_audio_sem_colisao_de_logrecord() -> None:
    client = OpenAIClient(api_key="test-key", timeout_seconds=5)
    client._client = _FakeOpenAISdkForAudio()  # type: ignore[assignment]

    result = client.transcribe_audio(
        model="gpt-4o-mini-transcribe",
        audio_bytes=b"audio-bytes",
        filename="audio.webm",
        language="pt",
    )

    assert result == "texto transcrito de audio"

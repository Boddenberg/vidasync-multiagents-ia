from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.services.pdf_texto_service import PdfTextoService


class _FakeOpenAIClient:
    def extract_text_from_pdf(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        pdf_bytes: bytes,
        filename: str,
    ) -> str:
        assert model == "gpt-4o-mini"
        assert "agente OCR para transcricao de PDF" in system_prompt
        assert "pt-BR" in user_prompt
        assert filename == "plano.pdf"
        assert pdf_bytes.startswith(b"%PDF-")
        return "Plano alimentar\nCafe da manha: ovos"


def test_pdf_texto_service_transcreve_pdf() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PdfTextoService(settings=settings, client=_FakeOpenAIClient())  # type: ignore[arg-type]

    result = service.transcrever_pdf(
        pdf_bytes=b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n",
        nome_arquivo="plano.pdf",
        contexto="transcrever_texto_pdf",
        idioma="pt-BR",
    )

    assert result.contexto == "transcrever_texto_pdf"
    assert result.nome_arquivo == "plano.pdf"
    assert "Plano alimentar" in result.texto_transcrito
    assert result.agente.nome_agente == "agente_transcricao_pdf"


def test_pdf_texto_service_rejeita_arquivo_nao_pdf() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PdfTextoService(settings=settings, client=_FakeOpenAIClient())  # type: ignore[arg-type]

    try:
        service.transcrever_pdf(
            pdf_bytes=b"arquivo qualquer",
            nome_arquivo="plano.pdf",
            contexto="transcrever_texto_pdf",
            idioma="pt-BR",
        )
        assert False, "Esperava ServiceError para arquivo invalido."
    except ServiceError as exc:
        assert exc.status_code == 400
        assert "PDF valido" in exc.message

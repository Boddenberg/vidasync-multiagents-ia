from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.services.imagem_texto_service import ImagemTextoService


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.image_urls: list[str] = []

    def extract_text_from_image(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_url: str,
    ) -> str:
        assert model == "gpt-4o-mini"
        assert "agente OCR" in system_prompt
        self.image_urls.append(image_url)
        if image_url.endswith("nota-fiscal.png"):
            return "ITEM A - 10,00\nITEM B - 20,00"
        return "Lote 123\nValidade 10/10/2027"


def test_imagem_texto_service_transcreve_lote_em_paralelo() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = ImagemTextoService(settings=settings, client=_FakeOpenAIClient())  # type: ignore[arg-type]

    result = service.transcrever_textos_de_imagens(
        imagem_urls=[
            "https://example.com/nota-fiscal.png",
            "https://example.com/rotulo-produto.png",
        ],
        contexto="transcrever_texto_imagem",
        idioma="pt-BR",
    )

    assert result.contexto == "transcrever_texto_imagem"
    assert result.total_imagens == 2
    assert result.resultados[0].status == "sucesso"
    assert "ITEM A - 10,00" in result.resultados[0].texto_transcrito
    assert result.resultados[1].status == "sucesso"
    assert "Lote 123" in result.resultados[1].texto_transcrito
    assert result.agente.nome_agente == "agente_ocr_imagem_texto"
    assert result.agente.modo_execucao == "paralelo"


def test_imagem_texto_service_resolve_storage_key_sem_token() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        supabase_url="https://project.supabase.co",
        supabase_storage_public_bucket="pipeline-inputs",
    )
    fake_client = _FakeOpenAIClient()
    service = ImagemTextoService(settings=settings, client=fake_client)  # type: ignore[arg-type]

    result = service.transcrever_textos_de_imagens(
        imagem_urls=["file/abc/2026-03-08/nota-fiscal.png"],
        contexto="transcrever_texto_imagem",
        idioma="pt-BR",
    )

    expected_url = (
        "https://project.supabase.co/storage/v1/object/public/"
        "pipeline-inputs/file/abc/2026-03-08/nota-fiscal.png"
    )
    assert fake_client.image_urls == [expected_url]
    assert result.resultados[0].imagem_url == expected_url

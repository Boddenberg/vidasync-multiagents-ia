from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.services.imagem_texto_service import ImagemTextoService


class _FakeOpenAIClient:
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

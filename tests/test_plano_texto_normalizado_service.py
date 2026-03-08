from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.services.plano_texto_normalizado_service import PlanoTextoNormalizadoService


class _FakeOpenAIClient:
    def generate_json_from_image(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        image_url: str,
    ) -> dict:
        assert model == "gpt-4o-mini"
        assert "normalizar o conteudo em texto estruturado" in system_prompt
        assert "Tipo_fonte: imagem" in user_prompt
        assert image_url == "https://example.com/plano.png"
        return {
            "titulo_documento": "Plano Alimentar",
            "secoes": [
                {"titulo": "desjejum_07_00", "texto": "QTD: 1 unidade | ALIMENTO: Ovo"},
                {"titulo": "almoco_12_30", "texto": "QTD: 3 colheres de sopa | ALIMENTO: Arroz integral"},
            ],
            "texto_normalizado": "nao_usar_este_campo_quando_ha_secoes",
            "observacoes": ["coluna_com_ligeira_ambiguidade"],
        }

    def generate_json_from_pdf(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        pdf_bytes: bytes,
        filename: str,
    ) -> dict:
        assert model == "gpt-4o-mini"
        assert "Tipo_fonte: pdf" in user_prompt
        assert filename == "plano.pdf"
        assert pdf_bytes.startswith(b"%PDF-")
        return {
            "titulo_documento": "Plano Alimentar",
            "secoes": [
                {"titulo": "cabecalho", "texto": "Paciente: Leticia"},
                {"titulo": "desjejum_07_00", "texto": "QTD: 1 unidade | ALIMENTO: Ovo"},
            ],
            "texto_normalizado": "",
            "observacoes": [],
        }

    def generate_json_from_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        assert model == "gpt-4o-mini"
        assert "OCR literal" in user_prompt
        return {
            "titulo_documento": "Plano Alimentar",
            "secoes": [
                {"titulo": "desjejum", "texto": "QTD: 1 unidade  |  ALIMENTO: Ovo\nQTD: 1 unidade | ALIMENTO: Ovo"},
                {"titulo": "desjejum", "texto": "QTD: 1 unidade | ALIMENTO: Ovo"},
                {"titulo": "almoco", "texto": "QTD: 3 colheres de sopa | ALIMENTO: Arroz integral"},
            ],
            "observacoes": ["coluna_ambigua", "coluna_ambigua"],
        }


def test_plano_texto_normalizado_service_imagem() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PlanoTextoNormalizadoService(settings=settings, client=_FakeOpenAIClient())  # type: ignore[arg-type]

    result = service.normalizar_de_imagens(
        imagem_urls=["https://example.com/plano.png"],
        contexto="normalizar_texto_plano_alimentar",
        idioma="pt-BR",
    )

    assert result.tipo_fonte == "imagem"
    assert result.total_fontes == 1
    assert result.titulo_documento == "Plano Alimentar"
    assert len(result.secoes) == 2
    assert "QTD: 1 unidade | ALIMENTO: Ovo" in result.texto_normalizado
    assert result.observacoes == ["coluna_com_ligeira_ambiguidade"]


def test_plano_texto_normalizado_service_pdf() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PlanoTextoNormalizadoService(settings=settings, client=_FakeOpenAIClient())  # type: ignore[arg-type]

    result = service.normalizar_de_pdf(
        pdf_bytes=b"%PDF-1.7\nfake",
        nome_arquivo="plano.pdf",
        contexto="normalizar_texto_plano_alimentar",
        idioma="pt-BR",
    )

    assert result.tipo_fonte == "pdf"
    assert result.total_fontes == 1
    assert result.titulo_documento == "Plano Alimentar"
    assert len(result.secoes) == 2
    assert "Paciente: Leticia" in result.texto_normalizado


def test_plano_texto_normalizado_service_texto_deduplica_secoes_e_linhas() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    service = PlanoTextoNormalizadoService(settings=settings, client=_FakeOpenAIClient())  # type: ignore[arg-type]

    result = service.normalizar_de_textos(
        textos_fonte=["OCR literal: tabela nutricional"],
        contexto="normalizar_texto_plano_alimentar",
        idioma="pt-BR",
    )

    assert result.tipo_fonte == "texto_ocr"
    assert len(result.secoes) == 2
    assert result.secoes[0].titulo == "desjejum"
    assert result.secoes[0].texto.count("QTD: 1 unidade | ALIMENTO: Ovo") == 1
    assert result.observacoes == ["coluna_ambigua"]

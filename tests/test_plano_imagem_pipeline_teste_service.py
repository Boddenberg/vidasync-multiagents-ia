from datetime import datetime, timezone

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.schemas import (
    AgenteEstruturacaoPlano,
    AgenteNormalizacaoPlanoTexto,
    AgenteTranscricaoImagemTexto,
    ImagemTextoItemResponse,
    ImagemTextoResponse,
    PlanoAlimentarEstruturado,
    PlanoAlimentarResponse,
    PlanoTextoNormalizadoResponse,
    PlanoTextoNormalizadoSecao,
)
from vidasync_multiagents_ia.services.plano_imagem_pipeline_teste_service import (
    PlanoImagemPipelineTesteService,
)


class _FakeImagemTextoService:
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
            total_imagens=1,
            resultados=[
                ImagemTextoItemResponse(
                    imagem_url=imagem_urls[0],
                    status="sucesso",
                    texto_transcrito="ocr literal",
                )
            ],
            agente=AgenteTranscricaoImagemTexto(
                contexto="transcrever_texto_imagem",
                nome_agente="agente_ocr_imagem_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                modo_execucao="paralelo",
                total_imagens=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakePlanoTextoNormalizadoService:
    def __init__(self) -> None:
        self.called_texto = 0
        self.called_imagem = 0

    def normalizar_de_imagens(
        self,
        *,
        imagem_urls: list[str],
        contexto: str = "normalizar_texto_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoTextoNormalizadoResponse:
        self.called_imagem += 1
        return PlanoTextoNormalizadoResponse(
            contexto=contexto,
            idioma=idioma,
            tipo_fonte="imagem",
            total_fontes=1,
            titulo_documento="Plano Alimentar",
            secoes=[PlanoTextoNormalizadoSecao(titulo="desjejum", texto="QTD: 1 unidade | ALIMENTO: Ovo")],
            texto_normalizado="[desjejum]\nQTD: 1 unidade | ALIMENTO: Ovo",
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

    def normalizar_de_textos(
        self,
        *,
        textos_fonte: list[str],
        contexto: str = "normalizar_texto_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoTextoNormalizadoResponse:
        self.called_texto += 1
        assert textos_fonte == ["ocr literal"]
        return PlanoTextoNormalizadoResponse(
            contexto=contexto,
            idioma=idioma,
            tipo_fonte="texto_ocr",
            total_fontes=1,
            titulo_documento="Plano Alimentar",
            secoes=[PlanoTextoNormalizadoSecao(titulo="desjejum", texto="QTD: 1 unidade | ALIMENTO: Ovo")],
            texto_normalizado="[desjejum]\nQTD: 1 unidade | ALIMENTO: Ovo",
            observacoes=[],
            agente=AgenteNormalizacaoPlanoTexto(
                contexto="normalizar_texto_plano_alimentar",
                nome_agente="agente_normalizacao_plano_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                tipo_fonte="texto_ocr",
                total_fontes=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakePlanoAlimentarService:
    def estruturar_plano(
        self,
        *,
        textos_fonte: list[str],
        contexto: str = "estruturar_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoAlimentarResponse:
        assert textos_fonte == ["[desjejum]\nQTD: 1 unidade | ALIMENTO: Ovo"]
        return PlanoAlimentarResponse(
            contexto=contexto,
            idioma=idioma,
            fontes_processadas=1,
            plano_alimentar=PlanoAlimentarEstruturado(objetivos=["teste"]),
            agente=AgenteEstruturacaoPlano(
                contexto="estruturar_plano_alimentar",
                nome_agente="agente_estrutura_plano_alimentar",
                status="sucesso",
                modelo="gpt-4o-mini",
                fontes_processadas=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


def test_pipeline_teste_service_com_ocr_literal() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    normalizacao = _FakePlanoTextoNormalizadoService()
    service = PlanoImagemPipelineTesteService(
        settings=settings,
        imagem_service=_FakeImagemTextoService(),  # type: ignore[arg-type]
        normalizacao_service=normalizacao,  # type: ignore[arg-type]
        plano_service=_FakePlanoAlimentarService(),  # type: ignore[arg-type]
    )

    result = service.executar_pipeline(
        imagem_url="https://example.com/plano.png",
        executar_ocr_literal=True,
    )

    assert result.ocr_literal is not None
    assert result.texto_normalizado.titulo_documento == "Plano Alimentar"
    assert result.plano_estruturado.plano_alimentar.objetivos == ["teste"]
    assert result.texto_normalizado.tipo_fonte == "texto_ocr"
    assert result.agente.etapas_executadas == ["ocr_literal", "normalizacao_semantica", "estruturacao_plano"]
    assert normalizacao.called_texto == 1
    assert normalizacao.called_imagem == 0


def test_pipeline_teste_service_sem_ocr_literal() -> None:
    settings = Settings(openai_api_key="test-key", openai_model="gpt-4o-mini")
    normalizacao = _FakePlanoTextoNormalizadoService()
    service = PlanoImagemPipelineTesteService(
        settings=settings,
        imagem_service=_FakeImagemTextoService(),  # type: ignore[arg-type]
        normalizacao_service=normalizacao,  # type: ignore[arg-type]
        plano_service=_FakePlanoAlimentarService(),  # type: ignore[arg-type]
    )

    result = service.executar_pipeline(
        imagem_url="https://example.com/plano.png",
        executar_ocr_literal=False,
    )

    assert result.ocr_literal is None
    assert result.agente.etapas_executadas == ["normalizacao_semantica", "estruturacao_plano"]
    assert normalizacao.called_texto == 0
    assert normalizacao.called_imagem == 1

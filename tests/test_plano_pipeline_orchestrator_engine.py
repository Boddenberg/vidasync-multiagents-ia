from datetime import datetime, timezone

import pytest

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
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
from vidasync_multiagents_ia.services.plano_pipeline_e2e_teste_service import (
    PlanoPipelineE2ETesteService,
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
                    texto_transcrito="ocr literal imagem",
                )
            ],
            agente=AgenteTranscricaoImagemTexto(
                contexto=contexto,
                nome_agente="agente_ocr_imagem_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                modo_execucao="paralelo",
                total_imagens=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakePlanoTextoNormalizadoService:
    def normalizar_de_textos(
        self,
        *,
        textos_fonte: list[str],
        contexto: str = "normalizar_texto_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoTextoNormalizadoResponse:
        return PlanoTextoNormalizadoResponse(
            contexto=contexto,
            idioma=idioma,
            tipo_fonte="texto_ocr",
            total_fontes=1,
            titulo_documento="Plano",
            secoes=[PlanoTextoNormalizadoSecao(titulo="desjejum", texto="QTD: 1 unidade | ALIMENTO: Ovo")],
            texto_normalizado="[desjejum]\nQTD: 1 unidade | ALIMENTO: Ovo",
            observacoes=[],
            agente=AgenteNormalizacaoPlanoTexto(
                contexto=contexto,
                nome_agente="agente_normalizacao_plano_texto",
                status="sucesso",
                modelo="gpt-4o-mini",
                tipo_fonte="texto_ocr",
                total_fontes=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )

    def normalizar_de_imagens(
        self,
        *,
        imagem_urls: list[str],
        contexto: str = "normalizar_texto_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoTextoNormalizadoResponse:
        return self.normalizar_de_textos(textos_fonte=["x"], contexto=contexto, idioma=idioma)


class _FakePlanoAlimentarService:
    def estruturar_plano(
        self,
        *,
        textos_fonte: list[str],
        contexto: str = "estruturar_plano_alimentar",
        idioma: str = "pt-BR",
    ) -> PlanoAlimentarResponse:
        return PlanoAlimentarResponse(
            contexto=contexto,
            idioma=idioma,
            fontes_processadas=1,
            plano_alimentar=PlanoAlimentarEstruturado(objetivos=["ok"]),
            agente=AgenteEstruturacaoPlano(
                contexto=contexto,
                nome_agente="agente_estrutura_plano_alimentar",
                status="sucesso",
                modelo="gpt-4o-mini",
                fontes_processadas=1,
            ),
            extraido_em=datetime(2026, 3, 7, 0, 0, 0, tzinfo=timezone.utc),
        )


class _FakePdfTextoService:
    def transcrever_pdf(self, **kwargs):  # noqa: ANN003
        raise AssertionError("Nao deveria ser chamado neste teste")


@pytest.mark.parametrize("engine", ["legacy", "langgraph"])
def test_plano_pipeline_orchestrator_engine_switch(engine: str) -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        plano_pipeline_orchestrator_engine=engine,
    )
    service = PlanoPipelineE2ETesteService(
        settings=settings,
        imagem_service=_FakeImagemTextoService(),  # type: ignore[arg-type]
        pdf_service=_FakePdfTextoService(),  # type: ignore[arg-type]
        normalizacao_service=_FakePlanoTextoNormalizadoService(),  # type: ignore[arg-type]
        plano_service=_FakePlanoAlimentarService(),  # type: ignore[arg-type]
    )

    result = service.executar_pipeline_imagem(imagem_url="https://example.com/plano.png")

    assert result.tipo_fonte == "imagem"
    assert result.temporario is True
    assert result.agente.etapas_executadas == ["ocr_literal", "normalizacao_semantica", "estruturacao_plano"]


def test_plano_pipeline_orchestrator_engine_invalido() -> None:
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        plano_pipeline_orchestrator_engine="invalido",
    )
    with pytest.raises(ServiceError):
        PlanoPipelineE2ETesteService(
            settings=settings,
            imagem_service=_FakeImagemTextoService(),  # type: ignore[arg-type]
            pdf_service=_FakePdfTextoService(),  # type: ignore[arg-type]
            normalizacao_service=_FakePlanoTextoNormalizadoService(),  # type: ignore[arg-type]
            plano_service=_FakePlanoAlimentarService(),  # type: ignore[arg-type]
        )

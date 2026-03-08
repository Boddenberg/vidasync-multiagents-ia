import logging

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.schemas import PlanoPipelineE2ETesteResponse
from vidasync_multiagents_ia.services.imagem_texto_service import ImagemTextoService
from vidasync_multiagents_ia.services.pdf_texto_service import PdfTextoService
from vidasync_multiagents_ia.services.plano_alimentar_service import PlanoAlimentarService
from vidasync_multiagents_ia.services.plano_texto_normalizado_service import (
    PlanoTextoNormalizadoService,
)
from vidasync_multiagents_ia.services.orchestration import (
    AiOrchestrator,
    PlanoPipelineExecutionInput,
    build_plano_pipeline_orchestrator,
)


class PlanoPipelineE2ETesteService:
    # /**** Endpoint TEMPORARIO: facade estavel para trocar engine (legacy/langgraph) sem mudar API. ****/
    def __init__(
        self,
        settings: Settings,
        imagem_service: ImagemTextoService | None = None,
        pdf_service: PdfTextoService | None = None,
        normalizacao_service: PlanoTextoNormalizadoService | None = None,
        plano_service: PlanoAlimentarService | None = None,
        orchestrator: AiOrchestrator | None = None,
    ) -> None:
        self._settings = settings
        self._imagem_service = imagem_service or ImagemTextoService(settings=settings)
        self._pdf_service = pdf_service or PdfTextoService(settings=settings)
        self._normalizacao_service = normalizacao_service or PlanoTextoNormalizadoService(settings=settings)
        self._plano_service = plano_service or PlanoAlimentarService(settings=settings)
        self._orchestrator = orchestrator or build_plano_pipeline_orchestrator(
            settings=settings,
            imagem_service=self._imagem_service,
            pdf_service=self._pdf_service,
            normalizacao_service=self._normalizacao_service,
            plano_service=self._plano_service,
        )
        self._logger = logging.getLogger(__name__)
        self._logger.info(
            "plano_pipeline_e2e.engine_selected",
            extra={"engine": settings.plano_pipeline_orchestrator_engine, "temporario": True},
        )

    def executar_pipeline_imagem(
        self,
        *,
        imagem_url: str,
        contexto: str = "pipeline_teste_plano_e2e",
        idioma: str = "pt-BR",
        executar_ocr_literal: bool = True,
    ) -> PlanoPipelineE2ETesteResponse:
        request = PlanoPipelineExecutionInput(
            tipo_fonte="imagem",
            contexto=contexto,
            idioma=idioma,
            executar_ocr_literal=executar_ocr_literal,
            imagem_url=imagem_url,
        )
        return self._orchestrator.execute_plano_pipeline(request=request)

    def executar_pipeline_pdf(
        self,
        *,
        pdf_bytes: bytes,
        nome_arquivo: str,
        contexto: str = "pipeline_teste_plano_e2e",
        idioma: str = "pt-BR",
        executar_ocr_literal: bool = True,
    ) -> PlanoPipelineE2ETesteResponse:
        request = PlanoPipelineExecutionInput(
            tipo_fonte="pdf",
            contexto=contexto,
            idioma=idioma,
            executar_ocr_literal=executar_ocr_literal,
            pdf_bytes=pdf_bytes,
            nome_arquivo=nome_arquivo,
        )
        return self._orchestrator.execute_plano_pipeline(request=request)

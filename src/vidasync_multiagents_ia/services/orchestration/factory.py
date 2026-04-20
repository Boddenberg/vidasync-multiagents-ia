from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.services.imagem_texto_service import ImagemTextoService
from vidasync_multiagents_ia.services.orchestration.ai_orchestrator import AiOrchestrator
from vidasync_multiagents_ia.services.orchestration.plano_pipeline_langgraph_orchestrator import (
    LangGraphPlanoPipelineOrchestrator,
)
from vidasync_multiagents_ia.services.orchestration.plano_pipeline_legacy_orchestrator import (
    LegacyPlanoPipelineOrchestrator,
)
from vidasync_multiagents_ia.services.pdf_texto_service import PdfTextoService
from vidasync_multiagents_ia.services.plano_alimentar_service import PlanoAlimentarService
from vidasync_multiagents_ia.services.plano_texto_normalizado_service import (
    PlanoTextoNormalizadoService,
)


def build_plano_pipeline_orchestrator(
    *,
    settings: Settings,
    imagem_service: ImagemTextoService,
    pdf_service: PdfTextoService,
    normalizacao_service: PlanoTextoNormalizadoService,
    plano_service: PlanoAlimentarService,
) -> AiOrchestrator:
    engine = settings.plano_pipeline_orchestrator_engine.strip().lower()
    if engine == "langgraph":
        return LangGraphPlanoPipelineOrchestrator(
            settings=settings,
            imagem_service=imagem_service,
            pdf_service=pdf_service,
            normalizacao_service=normalizacao_service,
            plano_service=plano_service,
        )
    if engine == "legacy":
        return LegacyPlanoPipelineOrchestrator(
            settings=settings,
            imagem_service=imagem_service,
            pdf_service=pdf_service,
            normalizacao_service=normalizacao_service,
            plano_service=plano_service,
        )
    raise ServiceError(
        "PLANO_PIPELINE_ORCHESTRATOR_ENGINE invalido. Use 'langgraph' ou 'legacy'.",
        status_code=500,
    )

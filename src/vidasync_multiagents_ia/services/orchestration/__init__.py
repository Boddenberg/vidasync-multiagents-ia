from typing import TYPE_CHECKING

from vidasync_multiagents_ia.services.orchestration.ai_orchestrator import (
    AiOrchestrator,
    PlanoPipelineExecutionInput,
)
from vidasync_multiagents_ia.services.orchestration.chat_orchestrator import (
    AiOrchestrator as ChatAiOrchestratorPort,
)
from vidasync_multiagents_ia.services.orchestration.chat_orchestrator import (
    AiOrchestratorRequest,
    AiOrchestratorResponse,
    ChatAiOrchestrator,
    ChatExecutionInput,
    ChatExecutionOutput,
)

if TYPE_CHECKING:
    from vidasync_multiagents_ia.clients import OpenAIClient
    from vidasync_multiagents_ia.config import Settings
    from vidasync_multiagents_ia.services.chat_conversacional_router_service import (
        ChatConversacionalRouterService,
    )
    from vidasync_multiagents_ia.services.chat_intencao_service import ChatIntencaoService
    from vidasync_multiagents_ia.services.chat_memory_service import ChatMemoryService
    from vidasync_multiagents_ia.services.imagem_texto_service import ImagemTextoService
    from vidasync_multiagents_ia.services.pdf_texto_service import PdfTextoService
    from vidasync_multiagents_ia.services.plano_alimentar_service import PlanoAlimentarService
    from vidasync_multiagents_ia.services.plano_texto_normalizado_service import (
        PlanoTextoNormalizadoService,
    )


def build_chat_orchestrator(
    *,
    settings: "Settings",
    intencao_service: "ChatIntencaoService",
    router_service: "ChatConversacionalRouterService",
    memory_service: "ChatMemoryService",
) -> ChatAiOrchestrator:
    # Import lazy para evitar ciclo com router durante bootstrap dos servicos.
    from vidasync_multiagents_ia.services.orchestration.chat_factory import (
        build_chat_orchestrator as _build_chat_orchestrator,
    )

    return _build_chat_orchestrator(
        settings=settings,
        intencao_service=intencao_service,
        router_service=router_service,
        memory_service=memory_service,
    )


def build_chat_ai_orchestrator(
    *,
    settings: "Settings",
    client: "OpenAIClient | None" = None,
    intencao_service: "ChatIntencaoService | None" = None,
    router_service: "ChatConversacionalRouterService | None" = None,
    memory_service: "ChatMemoryService | None" = None,
) -> ChatAiOrchestratorPort:
    from vidasync_multiagents_ia.services.orchestration.chat_factory import (
        build_chat_ai_orchestrator as _build_chat_ai_orchestrator,
    )

    return _build_chat_ai_orchestrator(
        settings=settings,
        client=client,
        intencao_service=intencao_service,
        router_service=router_service,
        memory_service=memory_service,
    )


def build_plano_pipeline_orchestrator(
    *,
    settings: "Settings",
    imagem_service: "ImagemTextoService",
    pdf_service: "PdfTextoService",
    normalizacao_service: "PlanoTextoNormalizadoService",
    plano_service: "PlanoAlimentarService",
) -> AiOrchestrator:
    # Import lazy para manter __init__ leve e sem acoplamento com os factories concretos.
    from vidasync_multiagents_ia.services.orchestration.factory import (
        build_plano_pipeline_orchestrator as _build_plano_pipeline_orchestrator,
    )

    return _build_plano_pipeline_orchestrator(
        settings=settings,
        imagem_service=imagem_service,
        pdf_service=pdf_service,
        normalizacao_service=normalizacao_service,
        plano_service=plano_service,
    )


__all__ = [
    "AiOrchestrator",
    "PlanoPipelineExecutionInput",
    "ChatAiOrchestratorPort",
    "AiOrchestratorRequest",
    "AiOrchestratorResponse",
    "ChatAiOrchestrator",
    "ChatExecutionInput",
    "ChatExecutionOutput",
    "build_chat_orchestrator",
    "build_chat_ai_orchestrator",
    "build_plano_pipeline_orchestrator",
]

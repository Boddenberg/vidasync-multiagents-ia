from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.services.chat_conversacional_router_service import (
    ChatConversacionalRouterService,
)
from vidasync_multiagents_ia.services.chat_intencao_service import ChatIntencaoService
from vidasync_multiagents_ia.services.chat_memory_service import ChatMemoryService
from vidasync_multiagents_ia.services.orchestration.chat_langgraph_orchestrator import (
    LangGraphChatOrchestrator,
)
from vidasync_multiagents_ia.services.orchestration.chat_legacy_orchestrator import (
    LegacyChatOrchestrator,
)
from vidasync_multiagents_ia.services.orchestration.chat_orchestrator import AiOrchestrator


def build_chat_orchestrator(
    *,
    settings: Settings,
    intencao_service: ChatIntencaoService,
    router_service: ChatConversacionalRouterService,
    memory_service: ChatMemoryService,
) -> AiOrchestrator:
    # /**** Builder legado mantido por compatibilidade; prefere-se build_chat_ai_orchestrator. ****/
    return _build_engine_orchestrator(
        settings=settings,
        intencao_service=intencao_service,
        router_service=router_service,
        memory_service=memory_service,
    )


def build_chat_ai_orchestrator(
    *,
    settings: Settings,
    client: OpenAIClient | None = None,
    intencao_service: ChatIntencaoService | None = None,
    router_service: ChatConversacionalRouterService | None = None,
    memory_service: ChatMemoryService | None = None,
) -> AiOrchestrator:
    # /****
    #  * Builder publico estavel para consumidores externos.
    #  * Esconde wiring interno (router, memoria, engine) da camada consumidora.
    #  ****/
    resolved_intencao = intencao_service or ChatIntencaoService()
    resolved_memory = memory_service or ChatMemoryService(settings=settings)
    resolved_router = router_service or ChatConversacionalRouterService(
        settings=settings,
        client=client,
    )
    return _build_engine_orchestrator(
        settings=settings,
        intencao_service=resolved_intencao,
        router_service=resolved_router,
        memory_service=resolved_memory,
    )


def _build_engine_orchestrator(
    *,
    settings: Settings,
    intencao_service: ChatIntencaoService,
    router_service: ChatConversacionalRouterService,
    memory_service: ChatMemoryService,
) -> AiOrchestrator:
    engine = settings.chat_orchestrator_engine.strip().lower()
    if engine == "langgraph":
        return LangGraphChatOrchestrator(
            settings=settings,
            intencao_service=intencao_service,
            router_service=router_service,
            memory_service=memory_service,
        )
    if engine == "legacy":
        return LegacyChatOrchestrator(
            settings=settings,
            intencao_service=intencao_service,
            router_service=router_service,
            memory_service=memory_service,
        )
    raise ServiceError(
        "CHAT_ORCHESTRATOR_ENGINE invalido. Use 'langgraph' ou 'legacy'.",
        status_code=500,
    )

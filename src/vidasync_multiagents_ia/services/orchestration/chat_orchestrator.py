from dataclasses import dataclass
from typing import Any
from typing import Protocol

from vidasync_multiagents_ia.schemas import ChatMemoriaEstado, ChatRoteamento, IntencaoChatDetectada


@dataclass(slots=True)
class AiOrchestratorRequest:
    prompt: str
    idioma: str = "pt-BR"
    contexto: str = "chat_conversacional"
    conversation_id: str | None = None
    usar_memoria: bool = True
    metadados_conversa: dict[str, Any] | None = None
    plano_anexo: dict[str, Any] | None = None
    refeicao_anexo: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metadados_conversa is None:
            self.metadados_conversa = {}


@dataclass(slots=True)
class AiOrchestratorResponse:
    response: str
    intencao: IntencaoChatDetectada
    roteamento: ChatRoteamento
    pipeline_id: str
    etapas_executadas: list[str]
    conversation_id: str
    memoria: ChatMemoriaEstado | None = None


class AiOrchestrator(Protocol):
    # Interface publica estavel de orquestracao de chat.
    #
    # Objetivo:
    # - esconder detalhes de engine (LangGraph/legacy), tools e RAG
    # - permitir evolucao interna sem quebrar consumidores
    def orchestrate_chat(self, *, request: AiOrchestratorRequest) -> AiOrchestratorResponse:
        ...


# Aliases de compatibilidade para nao quebrar codigo legado no projeto.
ChatExecutionInput = AiOrchestratorRequest
ChatExecutionOutput = AiOrchestratorResponse
ChatAiOrchestrator = AiOrchestrator

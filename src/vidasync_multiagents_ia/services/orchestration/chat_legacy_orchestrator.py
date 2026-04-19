import logging
from time import perf_counter
from uuid import uuid4

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability import (
    record_chat_stage_duration,
    record_chat_timeout,
)
from vidasync_multiagents_ia.services.chat_conversacional_router_service import (
    ChatConversacionalRouterService,
)
from vidasync_multiagents_ia.services.chat_intencao_service import ChatIntencaoService
from vidasync_multiagents_ia.services.chat_memory_service import (
    ChatMemoryService,
    compose_prompt_with_memory,
)
from vidasync_multiagents_ia.services.orchestration.chat_orchestrator import (
    AiOrchestrator,
    AiOrchestratorRequest,
    AiOrchestratorResponse,
)


class LegacyChatOrchestrator(AiOrchestrator):
    # Orquestracao sequencial legada para fallback da engine de chat.
    def __init__(
        self,
        *,
        settings: Settings,
        intencao_service: ChatIntencaoService,
        router_service: ChatConversacionalRouterService,
        memory_service: ChatMemoryService,
    ) -> None:
        self._settings = settings
        self._intencao_service = intencao_service
        self._router_service = router_service
        self._memory_service = memory_service
        self._logger = logging.getLogger(__name__)

    def orchestrate_chat(self, *, request: AiOrchestratorRequest) -> AiOrchestratorResponse:
        started = perf_counter()
        prompt = request.prompt.strip()
        if not prompt:
            raise ServiceError("Campo 'prompt' e obrigatorio para chat conversacional.", status_code=400)

        pipeline_id = uuid4().hex
        conversation_id = request.conversation_id.strip() if request.conversation_id else uuid4().hex
        etapas = ["entrada", "detectar_intencao", "rotear_intencao", "executar_pipeline", "compor_resposta", "saida_final"]
        stage_durations_ms: dict[str, float] = {}
        prompt_contextualizado = prompt
        memoria_estado = None
        try:
            if request.usar_memoria and self._settings.chat_memory_enabled:
                stage_started = perf_counter()
                memoria_pre = self._memory_service.build_context(
                    conversation_id=conversation_id,
                    metadados_conversa=request.metadados_conversa,
                )
                prompt_contextualizado = compose_prompt_with_memory(
                    prompt_atual=prompt,
                    memoria_contexto=memoria_pre.context_text,
                )
                memoria_estado = memoria_pre.estado
                stage_durations_ms["memoria_pre"] = (perf_counter() - stage_started) * 1000.0

            stage_started = perf_counter()
            intencao = self._intencao_service.detectar(prompt)
            stage_durations_ms["detectar_intencao"] = (perf_counter() - stage_started) * 1000.0

            stage_started = perf_counter()
            route_result = self._router_service.route(
                prompt=prompt,
                intencao=intencao,
                prompt_contextualizado=prompt_contextualizado,
                plano_anexo=request.plano_anexo,
                refeicao_anexo=request.refeicao_anexo,
            )
            stage_durations_ms["executar_pipeline"] = (perf_counter() - stage_started) * 1000.0

            if request.usar_memoria and self._settings.chat_memory_enabled:
                stage_started = perf_counter()
                memoria_estado = self._memory_service.append_exchange(
                    conversation_id=conversation_id,
                    user_prompt=prompt,
                    assistant_response=route_result.response,
                    intencao=intencao.intencao,
                    pipeline=route_result.roteamento.pipeline,
                    metadados_conversa=request.metadados_conversa,
                )
                stage_durations_ms["memoria_pos"] = (perf_counter() - stage_started) * 1000.0
        except Exception as exc:
            timeout = _is_timeout_exception(exc)
            if timeout:
                record_chat_timeout(flow="chat_conversacional", stage="legacy_orquestrador")
            raise

        total_duration_ms = (perf_counter() - started) * 1000.0
        for stage, duration_ms in stage_durations_ms.items():
            record_chat_stage_duration(
                engine="legacy",
                stage=stage,
                status="ok",
                duration_ms=duration_ms,
            )
        self._logger.info(
            "chat_orchestrator.legacy.completed",
            extra={
                "pipeline_id": pipeline_id,
                "conversation_id": conversation_id,
                "engine": "legacy",
                "etapas_executadas": etapas,
                "intencao": intencao.intencao,
                "pipeline": route_result.roteamento.pipeline,
                "handler": route_result.roteamento.handler,
                "status": route_result.roteamento.status,
                "warnings": len(route_result.roteamento.warnings),
                "precisa_revisao": route_result.roteamento.precisa_revisao,
                "stage_durations_ms": {k: round(v, 4) for k, v in stage_durations_ms.items()},
                "total_duration_ms": round(total_duration_ms, 4),
            },
        )
        return AiOrchestratorResponse(
            response=route_result.response,
            intencao=intencao,
            roteamento=route_result.roteamento,
            pipeline_id=pipeline_id,
            etapas_executadas=etapas,
            conversation_id=conversation_id,
            memoria=memoria_estado,
        )

    # Compatibilidade retroativa com chamadas antigas enquanto migramos consumidores.
    def execute_chat(self, *, request: AiOrchestratorRequest) -> AiOrchestratorResponse:
        return self.orchestrate_chat(request=request)


def _is_timeout_exception(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        name = current.__class__.__name__.lower()
        message = str(current).lower()
        if "timeout" in name or "timed out" in message or "timeout" in message:
            return True
        current = current.__cause__ or current.__context__
    return False

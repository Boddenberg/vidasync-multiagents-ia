import logging
from time import perf_counter
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability import (
    record_chat_stage_duration,
    record_chat_timeout,
)
from vidasync_multiagents_ia.schemas import ChatMemoriaEstado, ChatPipelineNome, IntencaoChatDetectada
from vidasync_multiagents_ia.services.chat_conversacional_router_service import (
    ChatConversacionalRouteResult,
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


class _ChatState(TypedDict, total=False):
    request: AiOrchestratorRequest
    prompt_normalizado: str
    prompt_contextualizado: str
    plano_anexo: dict[str, Any] | None
    refeicao_anexo: dict[str, Any] | None
    pipeline_id: str
    conversation_id: str
    etapas_executadas: list[str]
    intencao: IntencaoChatDetectada
    pipeline_alvo: ChatPipelineNome
    handler_alvo: str
    route_result: ChatConversacionalRouteResult
    response_final: str
    memoria_estado: ChatMemoriaEstado | None
    stage_durations_ms: dict[str, float]


class LangGraphChatOrchestrator(AiOrchestrator):
    # Grafo base do chat conversacional: simples hoje, preparado para crescer por etapa.
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
        self._compiled_graph = self._build_graph()

    def orchestrate_chat(self, *, request: AiOrchestratorRequest) -> AiOrchestratorResponse:
        started = perf_counter()
        prompt = request.prompt.strip()
        if not prompt:
            raise ServiceError("Campo 'prompt' e obrigatorio para chat conversacional.", status_code=400)

        pipeline_id = uuid4().hex
        conversation_id = request.conversation_id.strip() if request.conversation_id else uuid4().hex
        prompt_contextualizado = prompt
        memoria_estado: ChatMemoriaEstado | None = None
        stage_durations_ms: dict[str, float] = {}
        if request.usar_memoria and self._settings.chat_memory_enabled:
            stage_started = perf_counter()
            memoria_pre = self._memory_service.build_context(
                conversation_id=conversation_id,
                metadados_conversa=request.metadados_conversa,
            )
            memoria_estado = memoria_pre.estado
            prompt_contextualizado = compose_prompt_with_memory(
                prompt_atual=prompt,
                memoria_contexto=memoria_pre.context_text,
            )
            stage_durations_ms["memoria_pre"] = (perf_counter() - stage_started) * 1000.0
        try:
            state = self._compiled_graph.invoke(
                _ChatState(
                    request=request,
                    prompt_normalizado=prompt,
                    prompt_contextualizado=prompt_contextualizado,
                    plano_anexo=request.plano_anexo,
                    refeicao_anexo=request.refeicao_anexo,
                    pipeline_id=pipeline_id,
                    conversation_id=conversation_id,
                    etapas_executadas=[],
                    memoria_estado=memoria_estado,
                    stage_durations_ms=stage_durations_ms,
                )
            )
        except Exception as exc:
            timeout = _is_timeout_exception(exc)
            if timeout:
                record_chat_timeout(flow="chat_conversacional", stage="langgraph_orquestrador")
            raise

        intencao = state.get("intencao")
        route_result = state.get("route_result")
        response_final = state.get("response_final")
        conversation_id = state.get("conversation_id", conversation_id)
        etapas = state.get("etapas_executadas", [])
        stage_durations_ms = dict(state.get("stage_durations_ms", stage_durations_ms))
        if intencao is None or route_result is None or response_final is None:
            raise ServiceError("Falha no pipeline LangGraph de chat conversacional.", status_code=502)
        if request.usar_memoria and self._settings.chat_memory_enabled:
            stage_started = perf_counter()
            memoria_estado = self._memory_service.append_exchange(
                conversation_id=conversation_id,
                user_prompt=prompt,
                assistant_response=response_final,
                intencao=intencao.intencao,
                pipeline=route_result.roteamento.pipeline,
                metadados_conversa=request.metadados_conversa,
            )
            stage_durations_ms["memoria_pos"] = (perf_counter() - stage_started) * 1000.0

        total_duration_ms = (perf_counter() - started) * 1000.0
        for stage, duration_ms in stage_durations_ms.items():
            record_chat_stage_duration(
                engine="langgraph",
                stage=stage,
                status="ok",
                duration_ms=duration_ms,
            )

        self._logger.info(
            "chat_orchestrator.langgraph.completed",
            extra={
                "pipeline_id": pipeline_id,
                "conversation_id": conversation_id,
                "engine": "langgraph",
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
            response=response_final,
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

    def _build_graph(self):
        graph = StateGraph(_ChatState)
        graph.add_node("entrada", self._node_entrada)
        graph.add_node("detectar_intencao", self._node_detectar_intencao)
        graph.add_node("rotear_intencao", self._node_rotear_intencao)
        graph.add_node("executar_pipeline", self._node_executar_pipeline)
        graph.add_node("compor_resposta", self._node_compor_resposta)
        graph.add_node("saida_final", self._node_saida_final)

        graph.set_entry_point("entrada")
        graph.add_edge("entrada", "detectar_intencao")
        graph.add_edge("detectar_intencao", "rotear_intencao")
        graph.add_edge("rotear_intencao", "executar_pipeline")
        graph.add_edge("executar_pipeline", "compor_resposta")
        graph.add_edge("compor_resposta", "saida_final")
        graph.add_edge("saida_final", END)
        return graph.compile()

    def _node_entrada(self, state: _ChatState) -> _ChatState:
        started = perf_counter()
        etapas = list(state.get("etapas_executadas", []))
        etapas.append("entrada")
        durations = dict(state.get("stage_durations_ms", {}))
        durations["entrada"] = (perf_counter() - started) * 1000.0
        return _ChatState(etapas_executadas=etapas, stage_durations_ms=durations)

    def _node_detectar_intencao(self, state: _ChatState) -> _ChatState:
        started = perf_counter()
        prompt = state.get("prompt_normalizado", "")
        etapas = list(state.get("etapas_executadas", []))
        intencao = self._intencao_service.detectar(prompt)
        etapas.append("detectar_intencao")
        durations = dict(state.get("stage_durations_ms", {}))
        durations["detectar_intencao"] = (perf_counter() - started) * 1000.0
        return _ChatState(intencao=intencao, etapas_executadas=etapas, stage_durations_ms=durations)

    def _node_rotear_intencao(self, state: _ChatState) -> _ChatState:
        started = perf_counter()
        intencao = state.get("intencao")
        prompt = state.get("prompt_normalizado", "")
        if intencao is None:
            raise ServiceError("Intencao nao detectada no fluxo de chat.", status_code=502)
        etapas = list(state.get("etapas_executadas", []))
        pipeline_alvo, handler_alvo = self._router_service.describe_route_for_intencao(
            intencao.intencao,
            prompt=prompt,
        )
        etapas.append("rotear_intencao")
        durations = dict(state.get("stage_durations_ms", {}))
        durations["rotear_intencao"] = (perf_counter() - started) * 1000.0
        return _ChatState(
            pipeline_alvo=pipeline_alvo,
            handler_alvo=handler_alvo,
            etapas_executadas=etapas,
            stage_durations_ms=durations,
        )

    def _node_executar_pipeline(self, state: _ChatState) -> _ChatState:
        started = perf_counter()
        intencao = state.get("intencao")
        prompt = state.get("prompt_normalizado", "")
        prompt_contextualizado = state.get("prompt_contextualizado")
        plano_anexo = state.get("plano_anexo")
        refeicao_anexo = state.get("refeicao_anexo")
        if intencao is None:
            raise ServiceError("Intencao nao detectada no fluxo de chat.", status_code=502)
        etapas = list(state.get("etapas_executadas", []))
        route_result = self._router_service.route(
            prompt=prompt,
            intencao=intencao,
            prompt_contextualizado=prompt_contextualizado,
            plano_anexo=plano_anexo,
            refeicao_anexo=refeicao_anexo,
        )
        etapas.append("executar_pipeline")
        durations = dict(state.get("stage_durations_ms", {}))
        durations["executar_pipeline"] = (perf_counter() - started) * 1000.0
        return _ChatState(route_result=route_result, etapas_executadas=etapas, stage_durations_ms=durations)

    def _node_compor_resposta(self, state: _ChatState) -> _ChatState:
        started = perf_counter()
        route_result = state.get("route_result")
        if route_result is None:
            raise ServiceError("Pipeline de chat nao retornou resultado.", status_code=502)
        etapas = list(state.get("etapas_executadas", []))
        # Ponto unico para futuras politicas de composicao (judge, guardrails, estilo de resposta).
        response_final = route_result.response.strip()
        etapas.append("compor_resposta")
        durations = dict(state.get("stage_durations_ms", {}))
        durations["compor_resposta"] = (perf_counter() - started) * 1000.0
        return _ChatState(response_final=response_final, etapas_executadas=etapas, stage_durations_ms=durations)

    def _node_saida_final(self, state: _ChatState) -> _ChatState:
        started = perf_counter()
        etapas = list(state.get("etapas_executadas", []))
        etapas.append("saida_final")
        durations = dict(state.get("stage_durations_ms", {}))
        durations["saida_final"] = (perf_counter() - started) * 1000.0
        return _ChatState(etapas_executadas=etapas, stage_durations_ms=durations)


def _is_timeout_exception(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        name = current.__class__.__name__.lower()
        message = str(current).lower()
        if "timeout" in name or "timed out" in message or "timeout" in message:
            return True
        current = current.__cause__ or current.__context__
    return False

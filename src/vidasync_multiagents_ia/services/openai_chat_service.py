import logging
from time import perf_counter
from typing import Any

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.observability import (
    record_chat_flow_execution,
    record_chat_timeout,
)
from vidasync_multiagents_ia.observability.payload_preview import preview_text
from vidasync_multiagents_ia.schemas import OpenAIChatResponse
from vidasync_multiagents_ia.services.orchestration import (
    AiOrchestratorRequest,
    ChatAiOrchestratorPort,
    build_chat_ai_orchestrator,
)


class OpenAIChatService:
    def __init__(
        self,
        settings: Settings,
        client: OpenAIClient | None = None,
        chat_intencao_service: Any | None = None,
        chat_router_service: Any | None = None,
        chat_memory_service: Any | None = None,
        chat_orchestrator: ChatAiOrchestratorPort | None = None,
    ) -> None:
        self._settings = settings
        # /****
        #  * OpenAIChatService depende apenas da porta estavel de orquestracao.
        #  * O wiring interno (intencao/router/memoria/engine) fica encapsulado no builder.
        #  ****/
        self._chat_orchestrator = chat_orchestrator or build_chat_ai_orchestrator(
            settings=settings,
            client=client,
            intencao_service=chat_intencao_service,
            router_service=chat_router_service,
            memory_service=chat_memory_service,
        )
        self._logger = logging.getLogger(__name__)

    def chat(
        self,
        prompt: str,
        *,
        conversation_id: str | None = None,
        usar_memoria: bool = True,
        metadados_conversa: dict[str, str] | None = None,
        plano_anexo: dict[str, Any] | None = None,
        refeicao_anexo: dict[str, Any] | None = None,
    ) -> OpenAIChatResponse:
        started = perf_counter()
        self._logger.info(
            "openai_chat.started",
            extra={
                "model": self._settings.openai_model,
                "prompt_chars": len(prompt),
                "conversation_id": conversation_id,
                "usar_memoria": usar_memoria,
                "plano_anexo_presente": bool(plano_anexo),
                "refeicao_anexo_presente": bool(refeicao_anexo),
                "prompt_preview": preview_text(
                    prompt,
                    max_chars=self._settings.log_internal_max_body_chars,
                )
                if self._settings.log_internal_payloads
                else None,
            },
        )
        try:
            output = self._chat_orchestrator.orchestrate_chat(
                request=AiOrchestratorRequest(
                    prompt=prompt,
                    idioma="pt-BR",
                    conversation_id=conversation_id,
                    usar_memoria=usar_memoria,
                    metadados_conversa=metadados_conversa or {},
                    plano_anexo=plano_anexo,
                    refeicao_anexo=refeicao_anexo,
                ),
            )
        except Exception as exc:
            duration_ms = (perf_counter() - started) * 1000.0
            timeout = _is_timeout_exception(exc)
            self._logger.exception(
                "openai_chat.failed",
                extra={
                    "duration_ms": round(duration_ms, 4),
                    "timeout": timeout,
                    "conversation_id": conversation_id,
                    "plano_anexo_presente": bool(plano_anexo),
                    "refeicao_anexo_presente": bool(refeicao_anexo),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            record_chat_flow_execution(
                flow="chat_conversacional",
                engine=self._settings.chat_orchestrator_engine,
                intencao="indefinida",
                pipeline="indefinido",
                handler="indefinido",
                status="erro",
                duration_ms=duration_ms,
            )
            if timeout:
                record_chat_timeout(flow="chat_conversacional", stage="orquestracao")
            raise

        duration_ms = (perf_counter() - started) * 1000.0

        self._logger.info(
            "openai_chat.completed",
            extra={
                "response_chars": len(output.response),
                "pipeline_id": output.pipeline_id,
                "etapas_executadas": output.etapas_executadas,
                "intencao_detectada": output.intencao.intencao,
                "pipeline": output.roteamento.pipeline,
                "handler": output.roteamento.handler,
                "status": output.roteamento.status,
                "conversation_id": output.conversation_id,
                "memory_turns": output.memoria.total_turnos if output.memoria else 0,
                "warnings": len(output.roteamento.warnings),
                "precisa_revisao": output.roteamento.precisa_revisao,
                "response_preview": preview_text(
                    output.response,
                    max_chars=self._settings.log_internal_max_body_chars,
                )
                if self._settings.log_internal_payloads
                else None,
                "duration_ms": round(duration_ms, 4),
            },
        )
        record_chat_flow_execution(
            flow="chat_conversacional",
            engine=self._settings.chat_orchestrator_engine,
            intencao=output.intencao.intencao,
            pipeline=output.roteamento.pipeline,
            handler=output.roteamento.handler,
            status=output.roteamento.status,
            duration_ms=duration_ms,
        )
        return OpenAIChatResponse(
            model=self._settings.openai_model,
            response=output.response,
            intencao_detectada=output.intencao,
            roteamento=output.roteamento,
            conversation_id=output.conversation_id,
            memoria=output.memoria,
        )


def _is_timeout_exception(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        name = current.__class__.__name__.lower()
        message = str(current).lower()
        if "timeout" in name or "timed out" in message or "timeout" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


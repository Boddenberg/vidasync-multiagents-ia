import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable, Literal

from langchain_core.documents import Document

from vidasync_multiagents_ia.clients import OpenAIClient
from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability import (
    record_chat_fallback,
    record_chat_stage_duration,
    record_chat_timeout,
)
from vidasync_multiagents_ia.observability.payload_preview import preview_text
from vidasync_multiagents_ia.schemas import (
    ChatPipelineNome,
    ChatRoteamento,
    IntencaoChatCandidata,
    IntencaoChatDetectada,
    IntencaoChatNome,
)
from vidasync_multiagents_ia.services.calorias_texto_service import CaloriasTextoService
from vidasync_multiagents_ia.services.chat_calorias_macros_flow_service import (
    ChatCaloriasMacrosFlowOutput,
    ChatCaloriasMacrosFlowService,
)
from vidasync_multiagents_ia.services.chat_cadastro_refeicoes_flow_service import (
    ChatCadastroRefeicoesFlowOutput,
    ChatCadastroRefeicoesFlowService,
)
from vidasync_multiagents_ia.services.chat_plano_alimentar_multimodal_flow_service import (
    ChatPlanoAlimentarMultimodalFlowOutput,
    ChatPlanoAlimentarMultimodalFlowService,
)
from vidasync_multiagents_ia.services.chat_refeicao_multimodal_flow_service import (
    ChatRefeicaoMultimodalFlowOutput,
    ChatRefeicaoMultimodalFlowService,
)
from vidasync_multiagents_ia.services.chat_receitas_flow_service import (
    ChatReceitasFlowOutput,
    ChatReceitasFlowService,
)
from vidasync_multiagents_ia.services.chat_substituicoes_flow_service import (
    ChatSubstituicoesFlowOutput,
    ChatSubstituicoesFlowService,
)
from vidasync_multiagents_ia.services.chat_tools import (
    ChatToolExecutionInput,
    ChatToolExecutionOutput,
    ChatToolExecutor,
    ChatToolName,
    build_chat_tool_executor,
)
from vidasync_multiagents_ia.services.plano_alimentar_service import PlanoAlimentarService
from vidasync_multiagents_ia.services.plano_texto_normalizado_service import PlanoTextoNormalizadoService


@dataclass(slots=True)
class ChatConversacionalRouteResult:
    response: str
    roteamento: ChatRoteamento


@dataclass(frozen=True, slots=True)
class _IntentHandler:
    pipeline: ChatPipelineNome
    nome_handler: str
    executor: Callable[[str, IntencaoChatDetectada, dict[str, Any] | None], "_HandlerPayload"]


@dataclass(slots=True)
class _HandlerPayload:
    response: str
    status: Literal["sucesso", "parcial", "erro"] = "sucesso"
    warnings: list[str] = field(default_factory=list)
    precisa_revisao: bool = False
    metadados: dict[str, Any] = field(default_factory=dict)
    handler_override: str | None = None


class ChatConversacionalRouterService:
    def __init__(
        self,
        *,
        settings: Settings,
        client: OpenAIClient | None = None,
        calorias_texto_service: CaloriasTextoService | None = None,
        plano_texto_normalizado_service: PlanoTextoNormalizadoService | None = None,
        plano_alimentar_service: PlanoAlimentarService | None = None,
        calorias_macros_flow_service: ChatCaloriasMacrosFlowService | None = None,
        cadastro_refeicoes_flow_service: ChatCadastroRefeicoesFlowService | None = None,
        plano_alimentar_multimodal_flow_service: ChatPlanoAlimentarMultimodalFlowService | None = None,
        refeicao_multimodal_flow_service: ChatRefeicaoMultimodalFlowService | None = None,
        receitas_flow_service: ChatReceitasFlowService | None = None,
        substituicoes_flow_service: ChatSubstituicoesFlowService | None = None,
        rag_retriever: Callable[[str], list[Document]] | None = None,
        tool_executor: ChatToolExecutor | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or OpenAIClient(
            api_key=settings.openai_api_key,
            timeout_seconds=settings.openai_timeout_seconds,
            log_payloads=settings.log_external_payloads,
            log_max_chars=settings.log_external_max_body_chars,
        )
        self._calorias_texto_service = calorias_texto_service or CaloriasTextoService(
            settings=settings,
            client=self._client,
        )
        self._plano_texto_normalizado_service = plano_texto_normalizado_service or PlanoTextoNormalizadoService(
            settings=settings,
            client=self._client,
        )
        self._plano_alimentar_service = plano_alimentar_service or PlanoAlimentarService(
            settings=settings,
            client=self._client,
        )
        self._receitas_flow_service = receitas_flow_service or ChatReceitasFlowService(
            settings=settings,
            client=self._client,
        )
        self._tool_executor = tool_executor or build_chat_tool_executor(
            settings=settings,
            client=self._client,
            calorias_service=self._calorias_texto_service,
            rag_retriever=rag_retriever,
        )
        self._calorias_macros_flow_service = calorias_macros_flow_service or ChatCaloriasMacrosFlowService(
            settings=settings,
            tool_executor=self._tool_executor,
            calorias_service=self._calorias_texto_service,
        )
        self._cadastro_refeicoes_flow_service = cadastro_refeicoes_flow_service or ChatCadastroRefeicoesFlowService(
            settings=settings,
            client=self._client,
            tool_runner=self._run_tool_fallback_cadastrar_prato,
        )
        self._plano_alimentar_multimodal_flow_service = (
            plano_alimentar_multimodal_flow_service
            or ChatPlanoAlimentarMultimodalFlowService(
                settings=settings,
                plano_texto_normalizado_service=self._plano_texto_normalizado_service,
                plano_alimentar_service=self._plano_alimentar_service,
            )
        )
        self._refeicao_multimodal_flow_service = refeicao_multimodal_flow_service or ChatRefeicaoMultimodalFlowService(
            settings=settings,
        )
        self._substituicoes_flow_service = substituicoes_flow_service or ChatSubstituicoesFlowService(
            settings=settings,
            client=self._client,
        )
        self._logger = logging.getLogger(__name__)
        self._handlers = self._build_handlers()

    def describe_route_for_intencao(
        self,
        intencao: IntencaoChatNome,
        *,
        prompt: str | None = None,
    ) -> tuple[ChatPipelineNome, str]:
        # /**** Exposicao controlada do registry para etapa de roteamento no orquestrador de chat. ****/
        handler = self._handlers.get(intencao, self._handlers["conversa_geral"])
        return handler.pipeline, handler.nome_handler

    def route(
        self,
        *,
        prompt: str,
        intencao: IntencaoChatDetectada,
        prompt_contextualizado: str | None = None,
        plano_anexo: dict[str, Any] | None = None,
        refeicao_anexo: dict[str, Any] | None = None,
    ) -> ChatConversacionalRouteResult:
        # /**** Roteador central por intencao: evita ifs espalhados e facilita adicionar novos handlers/tools. ****/
        intencao_efetiva, motivo_forcamento_anexo = self._resolve_intencao_para_anexos(
            intencao=intencao,
            plano_anexo=plano_anexo,
            refeicao_anexo=refeicao_anexo,
        )
        intencao_forcada_por_anexo = motivo_forcamento_anexo is not None
        handler = self._handlers.get(intencao_efetiva.intencao, self._handlers["conversa_geral"])
        prompt_para_handler = self._resolve_prompt_for_handler(
            prompt=prompt,
            intencao=intencao_efetiva.intencao,
            prompt_contextualizado=prompt_contextualizado,
        )
        anexo_para_handler = self._resolve_anexo_para_handler(
            intencao=intencao_efetiva.intencao,
            plano_anexo=plano_anexo,
            refeicao_anexo=refeicao_anexo,
        )
        self._logger.info(
            "chat_router.started",
            extra={
                "intencao_entrada": intencao.intencao,
                "confianca_entrada": intencao.confianca,
                "intencao": intencao_efetiva.intencao,
                "confianca": intencao_efetiva.confianca,
                "metodo_intencao": intencao_efetiva.metodo,
                "pipeline": handler.pipeline,
                "handler": handler.nome_handler,
                "prompt_chars": len(prompt),
                "prompt_contextualizado_chars": len(prompt_contextualizado or ""),
                "usar_prompt_contextualizado": prompt_para_handler != prompt,
                "plano_anexo_presente": bool(plano_anexo),
                "refeicao_anexo_presente": bool(refeicao_anexo),
                "intencao_forcada_por_anexo": intencao_forcada_por_anexo,
                "motivo_forcamento_anexo": motivo_forcamento_anexo,
            },
        )
        handler_started = perf_counter()
        try:
            payload = handler.executor(prompt_para_handler, intencao_efetiva, anexo_para_handler)
            handler_duration_ms = (perf_counter() - handler_started) * 1000.0
            payload.metadados["handler_duration_ms"] = round(handler_duration_ms, 4)
            if intencao_forcada_por_anexo:
                payload.metadados["intencao_entrada"] = intencao.intencao
                payload.metadados["intencao_roteada"] = intencao_efetiva.intencao
                payload.metadados["intencao_forcada_por_anexo"] = True
                payload.metadados["motivo_forcamento_anexo"] = motivo_forcamento_anexo
            record_chat_stage_duration(
                engine=self._settings.chat_orchestrator_engine,
                stage=f"router.{handler.nome_handler}",
                status=payload.status,
                duration_ms=handler_duration_ms,
            )
            return self._build_result(handler, payload)
        except Exception as exc:  # noqa: BLE001
            handler_duration_ms = (perf_counter() - handler_started) * 1000.0
            timeout = _is_timeout_exception(exc)
            self._logger.exception(
                "chat_router.failed",
                extra={
                    "intencao": intencao_efetiva.intencao,
                    "pipeline": handler.pipeline,
                    "handler": handler.nome_handler,
                    "handler_duration_ms": round(handler_duration_ms, 4),
                    "timeout": timeout,
                },
            )
            record_chat_stage_duration(
                engine=self._settings.chat_orchestrator_engine,
                stage=f"router.{handler.nome_handler}",
                status="erro",
                duration_ms=handler_duration_ms,
            )
            record_chat_fallback(flow="chat_conversacional", reason="router_exception")
            if timeout:
                record_chat_timeout(flow="chat_conversacional", stage=f"router.{handler.nome_handler}")
            fallback_handler = self._handlers["conversa_geral"]
            fallback_payload = self._handle_conversa_geral(prompt, intencao_efetiva, None)
            fallback_payload.status = "parcial"
            fallback_payload.precisa_revisao = True
            fallback_payload.warnings.append("Falha no pipeline principal; resposta geral aplicada.")
            fallback_payload.metadados["fallback_de_intencao"] = intencao_efetiva.intencao
            fallback_payload.metadados["fallback_de_handler"] = handler.nome_handler
            return self._build_result(fallback_handler, fallback_payload)

    def _resolve_intencao_para_anexos(
        self,
        *,
        intencao: IntencaoChatDetectada,
        plano_anexo: dict[str, Any] | None,
        refeicao_anexo: dict[str, Any] | None,
    ) -> tuple[IntencaoChatDetectada, str | None]:
        # /**** Regras de prioridade de anexo: plano > refeicao (imagem/audio). ****/
        if plano_anexo and intencao.intencao != "enviar_plano_nutri":
            return self._override_intencao(
                intencao=intencao,
                destino="enviar_plano_nutri",
                contexto_roteamento="pipeline_plano_alimentar",
            ), "plano_anexo"

        tipo_refeicao = str((refeicao_anexo or {}).get("tipo_fonte") or "").strip().lower()
        if tipo_refeicao == "imagem" and intencao.intencao != "registrar_refeicao_foto":
            return self._override_intencao(
                intencao=intencao,
                destino="registrar_refeicao_foto",
                contexto_roteamento="estimar_porcoes_do_prato",
            ), "refeicao_anexo_imagem"
        if tipo_refeicao == "audio" and intencao.intencao != "registrar_refeicao_audio":
            return self._override_intencao(
                intencao=intencao,
                destino="registrar_refeicao_audio",
                contexto_roteamento="transcrever_audio_usuario",
            ), "refeicao_anexo_audio"
        return intencao, None

    def _override_intencao(
        self,
        *,
        intencao: IntencaoChatDetectada,
        destino: IntencaoChatNome,
        contexto_roteamento: str,
    ) -> IntencaoChatDetectada:
        candidatos: list[IntencaoChatCandidata] = []
        candidatos.append(IntencaoChatCandidata(intencao=intencao.intencao, confianca=intencao.confianca))
        for candidato in intencao.candidatos:
            if candidato.intencao == intencao.intencao:
                continue
            candidatos.append(candidato)
        candidatos = candidatos[:3]

        return IntencaoChatDetectada(
            intencao=destino,
            confianca=max(0.9, intencao.confianca),
            contexto_roteamento=contexto_roteamento,
            requer_fluxo_estruturado=True,
            metodo=f"{intencao.metodo}+anexo_override_v1",
            candidatos=candidatos,
        )

    def _resolve_anexo_para_handler(
        self,
        *,
        intencao: IntencaoChatNome,
        plano_anexo: dict[str, Any] | None,
        refeicao_anexo: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if intencao == "enviar_plano_nutri":
            return plano_anexo
        if intencao in {"registrar_refeicao_foto", "registrar_refeicao_audio"}:
            return refeicao_anexo
        return None

    def _build_handlers(self) -> dict[IntencaoChatNome, _IntentHandler]:
        return {
            "enviar_plano_nutri": _IntentHandler(
                pipeline="pipeline_plano_alimentar",
                nome_handler="handler_fluxo_plano_alimentar_multimodal",
                executor=self._handle_fluxo_plano_alimentar_multimodal,
            ),
            "pedir_receitas": _IntentHandler(
                pipeline="rag_conhecimento_nutricional",
                nome_handler="handler_fluxo_receitas_personalizadas",
                executor=self._handle_fluxo_receitas,
            ),
            "pedir_substituicoes": _IntentHandler(
                pipeline="rag_conhecimento_nutricional",
                nome_handler="handler_fluxo_substituicoes_personalizadas",
                executor=self._handle_fluxo_substituicoes,
            ),
            "pedir_dicas": _IntentHandler(
                pipeline="rag_conhecimento_nutricional",
                nome_handler="handler_tool_consultar_conhecimento_nutricional",
                executor=lambda prompt, intencao, _: self._run_tool("consultar_conhecimento_nutricional", prompt, intencao),
            ),
            "perguntar_calorias": _IntentHandler(
                pipeline="tool_calculo",
                nome_handler="handler_fluxo_calorias_macros",
                executor=self._handle_fluxo_calorias_macros,
            ),
            "cadastrar_pratos": _IntentHandler(
                pipeline="cadastro_pratos",
                nome_handler="handler_fluxo_cadastro_refeicoes",
                executor=self._handle_fluxo_cadastro_refeicoes,
            ),
            "calcular_imc": _IntentHandler(
                pipeline="tool_calculo",
                nome_handler="handler_tool_calcular_imc",
                executor=lambda prompt, intencao, _: self._run_tool("calcular_imc", prompt, intencao),
            ),
            "registrar_refeicao_foto": _IntentHandler(
                pipeline="cadastro_refeicoes",
                nome_handler="handler_cadastro_refeicao_foto",
                executor=self._handle_cadastro_refeicao_foto,
            ),
            "registrar_refeicao_audio": _IntentHandler(
                pipeline="cadastro_refeicoes",
                nome_handler="handler_cadastro_refeicao_audio",
                executor=self._handle_cadastro_refeicao_audio,
            ),
            "conversa_geral": _IntentHandler(
                pipeline="resposta_conversacional_geral",
                nome_handler="handler_conversa_geral",
                executor=self._handle_conversa_geral,
            ),
        }

    def _build_result(self, handler: _IntentHandler, payload: _HandlerPayload) -> ChatConversacionalRouteResult:
        handler_name = payload.handler_override or handler.nome_handler
        tool_name = _extract_tool_name(payload.metadados)
        rag_used, rag_docs = _extract_rag_usage(payload.metadados)
        warnings = payload.warnings[:8]
        self._logger.info(
            "chat_router.completed",
            extra={
                "pipeline": handler.pipeline,
                "handler": handler_name,
                "status": payload.status,
                "warnings": len(payload.warnings),
                "warnings_preview": warnings,
                "precisa_revisao": payload.precisa_revisao,
                "response_chars": len(payload.response),
                "tool_acionada": tool_name,
                "rag_usado": rag_used,
                "rag_docs_count": rag_docs,
                "handler_duration_ms": payload.metadados.get("handler_duration_ms"),
                "response_preview": preview_text(
                    payload.response,
                    max_chars=self._settings.log_internal_max_body_chars,
                )
                if self._settings.log_internal_payloads
                else None,
            },
        )
        if payload.metadados.get("route_fallback_applied") is True:
            record_chat_fallback(flow="chat_conversacional", reason="flow_fallback")
        return ChatConversacionalRouteResult(
            response=payload.response,
            roteamento=ChatRoteamento(
                pipeline=handler.pipeline,
                handler=handler_name,
                status=payload.status,
                warnings=payload.warnings,
                precisa_revisao=payload.precisa_revisao,
                metadados=payload.metadados,
            ),
        )

    def _handle_fluxo_calorias_macros(
        self,
        prompt: str,
        _: IntencaoChatDetectada,
        __: dict[str, Any] | None,
    ) -> _HandlerPayload:
        # /**** Roteia calorias/macros com estrategia hibrida: contextual, base estruturada ou tool. ****/
        flow_output: ChatCaloriasMacrosFlowOutput = self._calorias_macros_flow_service.executar(
            prompt=prompt,
            idioma="pt-BR",
        )
        return _HandlerPayload(
            response=flow_output.resposta,
            status="parcial" if flow_output.warnings else "sucesso",
            warnings=flow_output.warnings,
            precisa_revisao=flow_output.precisa_revisao,
            metadados=flow_output.metadados,
            handler_override=flow_output.handler_override,
        )

    def _handle_fluxo_receitas(
        self,
        prompt: str,
        _: IntencaoChatDetectada,
        __: dict[str, Any] | None,
    ) -> _HandlerPayload:
        flow_output: ChatReceitasFlowOutput = self._receitas_flow_service.executar(prompt=prompt, idioma="pt-BR")
        return _HandlerPayload(
            response=flow_output.resposta,
            status="parcial" if flow_output.warnings else "sucesso",
            warnings=flow_output.warnings,
            precisa_revisao=flow_output.precisa_revisao,
            metadados=flow_output.metadados,
        )

    def _handle_fluxo_substituicoes(
        self,
        prompt: str,
        _: IntencaoChatDetectada,
        __: dict[str, Any] | None,
    ) -> _HandlerPayload:
        flow_output: ChatSubstituicoesFlowOutput = self._substituicoes_flow_service.executar(
            prompt=prompt,
            idioma="pt-BR",
        )
        return _HandlerPayload(
            response=flow_output.resposta,
            status="parcial" if flow_output.warnings else "sucesso",
            warnings=flow_output.warnings,
            precisa_revisao=flow_output.precisa_revisao,
            metadados=flow_output.metadados,
        )

    def _handle_fluxo_cadastro_refeicoes(
        self,
        prompt: str,
        _: IntencaoChatDetectada,
        __: dict[str, Any] | None,
    ) -> _HandlerPayload:
        # /**** Fluxo dedicado para cadastro por texto livre, com confirmacao orientada para ambiguidade. ****/
        flow_output: ChatCadastroRefeicoesFlowOutput = self._cadastro_refeicoes_flow_service.executar(
            prompt=prompt,
            idioma="pt-BR",
            origem_entrada="texto_livre",
        )
        return _HandlerPayload(
            response=flow_output.resposta,
            status="parcial" if flow_output.warnings else "sucesso",
            warnings=flow_output.warnings,
            precisa_revisao=flow_output.precisa_revisao,
            metadados=flow_output.metadados,
        )

    def _handle_fluxo_plano_alimentar_multimodal(
        self,
        prompt: str,
        _: IntencaoChatDetectada,
        plano_anexo: dict[str, Any] | None,
    ) -> _HandlerPayload:
        # /**** Entrada de plano no chat: aceita texto, foto (url) ou PDF (base64) sem quebrar contrato. ****/
        flow_output: ChatPlanoAlimentarMultimodalFlowOutput = self._plano_alimentar_multimodal_flow_service.executar(
            prompt=prompt,
            idioma="pt-BR",
            plano_anexo=plano_anexo,
        )
        return _HandlerPayload(
            response=flow_output.resposta,
            status="parcial" if flow_output.warnings else "sucesso",
            warnings=flow_output.warnings,
            precisa_revisao=flow_output.precisa_revisao,
            metadados=flow_output.metadados,
        )

    def _handle_cadastro_refeicao_foto(
        self,
        prompt: str,
        __: IntencaoChatDetectada,
        refeicao_anexo: dict[str, Any] | None,
    ) -> _HandlerPayload:
        if not refeicao_anexo:
            return _HandlerPayload(
                response="Para registrar refeicao por foto, envie a imagem e eu aciono a analise de porcoes.",
                status="parcial",
                warnings=["Anexo de refeicao nao informado para fluxo de foto."],
                precisa_revisao=True,
                metadados={
                    "contexto_sugerido": "estimar_porcoes_do_prato",
                    "campos_esperados": ["refeicao_anexo.tipo_fonte=imagem", "refeicao_anexo.imagem_url"],
                },
            )
        flow_output: ChatRefeicaoMultimodalFlowOutput = self._refeicao_multimodal_flow_service.executar_foto(
            prompt=prompt,
            idioma="pt-BR",
            refeicao_anexo=refeicao_anexo,
        )
        return _HandlerPayload(
            response=flow_output.resposta,
            status="parcial" if flow_output.warnings else "sucesso",
            warnings=flow_output.warnings,
            precisa_revisao=flow_output.precisa_revisao,
            metadados=flow_output.metadados,
        )

    def _handle_cadastro_refeicao_audio(
        self,
        prompt: str,
        __: IntencaoChatDetectada,
        refeicao_anexo: dict[str, Any] | None,
    ) -> _HandlerPayload:
        if not refeicao_anexo:
            return _HandlerPayload(
                response="Para registrar refeicao por audio, envie a gravacao e eu aciono transcricao + interpretacao.",
                status="parcial",
                warnings=["Anexo de refeicao nao informado para fluxo de audio."],
                precisa_revisao=True,
                metadados={
                    "contexto_sugerido": "transcrever_audio_usuario",
                    "campos_esperados": [
                        "refeicao_anexo.tipo_fonte=audio",
                        "refeicao_anexo.audio_base64",
                    ],
                },
            )
        flow_output: ChatRefeicaoMultimodalFlowOutput = self._refeicao_multimodal_flow_service.executar_audio(
            prompt=prompt,
            idioma="pt-BR",
            refeicao_anexo=refeicao_anexo,
        )
        return _HandlerPayload(
            response=flow_output.resposta,
            status="parcial" if flow_output.warnings else "sucesso",
            warnings=flow_output.warnings,
            precisa_revisao=flow_output.precisa_revisao,
            metadados=flow_output.metadados,
        )

    def _handle_conversa_geral(
        self,
        prompt: str,
        _: IntencaoChatDetectada,
        __: dict[str, Any] | None,
    ) -> _HandlerPayload:
        self._ensure_openai_api_key()
        response = self._client.generate_text(model=self._settings.openai_model, prompt=prompt)
        return _HandlerPayload(response=response)

    def _run_tool(
        self,
        tool_name: ChatToolName,
        prompt: str,
        intencao: IntencaoChatDetectada,
    ) -> _HandlerPayload:
        output = self._tool_executor.execute(
            data=ChatToolExecutionInput(
                tool_name=tool_name,
                prompt=prompt,
                idioma="pt-BR",
                intencao=intencao,
            )
        )
        metadados = dict(output.metadados)
        metadados["tool_name"] = output.tool_name
        return _HandlerPayload(
            response=output.resposta,
            status=output.status,
            warnings=output.warnings,
            precisa_revisao=output.precisa_revisao,
            metadados=metadados,
            handler_override=f"handler_tool_{output.tool_name}",
        )

    def _run_tool_fallback_cadastrar_prato(self, prompt: str, idioma: str) -> ChatToolExecutionOutput:
        intencao = IntencaoChatDetectada(
            intencao="cadastrar_pratos",
            confianca=0.99,
            contexto_roteamento="cadastro_pratos",
            requer_fluxo_estruturado=True,
        )
        return self._tool_executor.execute(
            data=ChatToolExecutionInput(
                tool_name="cadastrar_prato",
                prompt=prompt,
                idioma=idioma,
                intencao=intencao,
            )
        )

    def _resolve_prompt_for_handler(
        self,
        *,
        prompt: str,
        intencao: IntencaoChatNome,
        prompt_contextualizado: str | None,
    ) -> str:
        if not prompt_contextualizado:
            return prompt
        if intencao in {"pedir_receitas", "pedir_substituicoes", "pedir_dicas", "conversa_geral"}:
            # /**** So usa contexto expandido em fluxos conversacionais/contextuais para nao afetar parsers deterministas. ****/
            return prompt_contextualizado
        return prompt

    def _ensure_openai_api_key(self) -> None:
        if not self._settings.openai_api_key.strip():
            raise ServiceError("OPENAI_API_KEY nao configurada no ambiente.", status_code=500)


def _extract_tool_name(metadados: dict[str, Any]) -> str | None:
    tool_name = metadados.get("tool_name")
    if isinstance(tool_name, str) and tool_name.strip():
        return tool_name.strip()
    tool_fallback = metadados.get("tool_fallback")
    if isinstance(tool_fallback, dict):
        nested = tool_fallback.get("metadados")
        if isinstance(nested, dict):
            maybe = nested.get("tool_name")
            if isinstance(maybe, str) and maybe.strip():
                return maybe.strip()
    return None


def _extract_rag_usage(metadados: dict[str, Any]) -> tuple[bool, int]:
    docs_count = 0
    explicit = metadados.get("rag_used")
    if isinstance(explicit, bool):
        docs = metadados.get("rag_documents_count")
        if isinstance(docs, int):
            docs_count = max(0, docs)
        return explicit, docs_count

    docs = metadados.get("documentos_rag")
    if isinstance(docs, list):
        docs_count = len(docs)
        return docs_count > 0, docs_count

    nested = metadados.get("tool_metadados")
    if isinstance(nested, dict):
        nested_docs = nested.get("documentos_rag")
        if isinstance(nested_docs, list):
            docs_count = len(nested_docs)
            return docs_count > 0, docs_count
    return False, 0


def _is_timeout_exception(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        name = current.__class__.__name__.lower()
        message = str(current).lower()
        if "timeout" in name or "timed out" in message or "timeout" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


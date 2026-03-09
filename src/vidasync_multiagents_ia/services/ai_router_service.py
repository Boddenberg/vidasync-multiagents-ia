import base64
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Callable

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.observability import record_ai_router_request, record_ai_router_timeout
from vidasync_multiagents_ia.observability.context import reset_trace_id, set_trace_id
from vidasync_multiagents_ia.observability.payload_preview import preview_json
from vidasync_multiagents_ia.schemas import AIRouterRequest, AIRouterResponse
from vidasync_multiagents_ia.services.audio_transcricao_service import AudioTranscricaoService
from vidasync_multiagents_ia.services.calorias_texto_service import CaloriasTextoService
from vidasync_multiagents_ia.services.foto_alimentos_service import FotoAlimentosService
from vidasync_multiagents_ia.services.openai_chat_service import OpenAIChatService
from vidasync_multiagents_ia.services.pdf_texto_service import PdfTextoService


@dataclass(slots=True)
class _RouteExecution:
    resultado: dict[str, Any]
    warnings: list[str]
    precisa_revisao: bool
    status: str = "sucesso"


class AIRouterService:
    def __init__(
        self,
        *,
        settings: Settings,
        openai_chat_service: OpenAIChatService,
        foto_alimentos_service: FotoAlimentosService,
        audio_transcricao_service: AudioTranscricaoService,
        pdf_texto_service: PdfTextoService,
        calorias_texto_service: CaloriasTextoService,
    ) -> None:
        self._settings = settings
        self._openai_chat_service = openai_chat_service
        self._foto_alimentos_service = foto_alimentos_service
        self._audio_transcricao_service = audio_transcricao_service
        self._pdf_texto_service = pdf_texto_service
        self._calorias_texto_service = calorias_texto_service
        self._logger = logging.getLogger(__name__)

    def route(self, request: AIRouterRequest) -> AIRouterResponse:
        started = perf_counter()
        stage = "validacao_entrada"
        trace_id = _resolve_trace_id(request.trace_id)
        trace_token = set_trace_id(trace_id)
        contexto = request.contexto.strip().lower()
        payload = request.payload or {}
        if not isinstance(payload, dict):
            reset_trace_id(trace_token)
            raise ServiceError("Campo 'payload' deve ser um objeto JSON.", status_code=400)

        self._logger.info(
            "ai_router.started",
            extra={
                "trace_id": trace_id,
                "contexto": contexto,
                "idioma": request.idioma,
                "payload_keys": sorted(payload.keys()),
                "payload_preview": preview_json(
                    payload,
                    max_chars=self._settings.log_internal_max_body_chars,
                )
                if self._settings.log_internal_payloads
                else None,
            },
        )
        try:
            resolve_started = perf_counter()
            stage = "resolver_handler"
            handler = self._resolve_handler(contexto)
            resolve_duration_ms = (perf_counter() - resolve_started) * 1000.0

            execute_started = perf_counter()
            stage = "executar_contexto"
            execution = handler(payload, request.idioma)
            execute_duration_ms = (perf_counter() - execute_started) * 1000.0

            response_build_started = perf_counter()
            stage = "montar_resposta"
            response = AIRouterResponse(
                trace_id=trace_id,
                contexto=contexto,
                status=execution.status,
                warnings=execution.warnings,
                precisa_revisao=execution.precisa_revisao,
                resultado=execution.resultado,
                erro=None,
                extraido_em=datetime.now(timezone.utc),
            )
            response_build_duration_ms = (perf_counter() - response_build_started) * 1000.0
            total_duration_ms = (perf_counter() - started) * 1000.0

            self._logger.info(
                "ai_router.completed",
                extra={
                    "trace_id": trace_id,
                    "contexto": contexto,
                    "status": execution.status,
                    "warnings": len(execution.warnings),
                    "precisa_revisao": execution.precisa_revisao,
                    "resultado_preview": preview_json(
                        execution.resultado,
                        max_chars=self._settings.log_internal_max_body_chars,
                    )
                    if self._settings.log_internal_payloads
                    else None,
                    "stage_resolver_handler_ms": round(resolve_duration_ms, 4),
                    "stage_executar_contexto_ms": round(execute_duration_ms, 4),
                    "stage_montar_resposta_ms": round(response_build_duration_ms, 4),
                    "duration_ms": round(total_duration_ms, 4),
                },
            )
            record_ai_router_request(contexto=contexto, status=execution.status, duration_ms=total_duration_ms)
            if execution.status == "parcial":
                self._logger.info(
                    "ai_router.warning",
                    extra={
                        "trace_id": trace_id,
                        "contexto": contexto,
                        "warnings": execution.warnings,
                        "precisa_revisao": execution.precisa_revisao,
                    },
                )
            return response
        except Exception as exc:
            total_duration_ms = (perf_counter() - started) * 1000.0
            timeout = _is_timeout_exception(exc)
            self._logger.exception(
                "ai_router.failed",
                extra={
                    "trace_id": trace_id,
                    "contexto": contexto,
                    "stage": stage,
                    "duration_ms": round(total_duration_ms, 4),
                    "timeout": timeout,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "payload_preview": preview_json(
                        payload,
                        max_chars=self._settings.log_internal_max_body_chars,
                    )
                    if self._settings.log_internal_payloads
                    else None,
                },
            )
            record_ai_router_request(contexto=contexto, status="erro", duration_ms=total_duration_ms)
            if timeout:
                record_ai_router_timeout(contexto=contexto)
            raise
        finally:
            reset_trace_id(trace_token)

    def _resolve_handler(self, contexto: str) -> Callable[[dict[str, Any], str], _RouteExecution]:
        handlers: dict[str, Callable[[dict[str, Any], str], _RouteExecution]] = {
            "chat": self._handle_chat,
            "openai_chat": self._handle_chat,
            "identificar_fotos": self._handle_identificar_fotos,
            "estimar_porcoes_do_prato": self._handle_estimar_porcoes,
            "transcrever_audio_usuario": self._handle_transcrever_audio,
            "transcrever_texto_pdf": self._handle_transcrever_pdf,
            "calcular_calorias_texto": self._handle_calcular_calorias,
        }
        handler = handlers.get(contexto)
        if handler:
            return handler
        raise ServiceError(
            "Contexto nao suportado no /ai/router. "
            "Use: chat, identificar_fotos, estimar_porcoes_do_prato, "
            "transcrever_audio_usuario, transcrever_texto_pdf, calcular_calorias_texto.",
            status_code=400,
        )

    def _handle_chat(self, payload: dict[str, Any], idioma: str) -> _RouteExecution:
        prompt = _pick_str(payload, "prompt", "mensagem", "texto")
        if not prompt:
            raise ServiceError("Payload invalido para contexto chat: informe 'prompt'.", status_code=400)
        conversation_id = _pick_str(payload, "conversation_id", "conversa_id")
        usar_memoria = _pick_bool(payload, "usar_memoria", default=True)
        metadados_conversa = payload.get("metadados_conversa")
        metadados_dict: dict[str, str] = {}
        if isinstance(metadados_conversa, dict):
            metadados_dict = {str(key): str(value) for key, value in metadados_conversa.items()}
        plano_anexo = payload.get("plano_anexo")
        plano_anexo_dict: dict[str, Any] | None = None
        if isinstance(plano_anexo, dict):
            plano_anexo_dict = plano_anexo
        refeicao_anexo = payload.get("refeicao_anexo")
        refeicao_anexo_dict: dict[str, Any] | None = None
        if isinstance(refeicao_anexo, dict):
            refeicao_anexo_dict = refeicao_anexo

        response = self._openai_chat_service.chat(
            prompt,
            conversation_id=conversation_id,
            usar_memoria=usar_memoria,
            metadados_conversa=metadados_dict,
            plano_anexo=plano_anexo_dict,
            refeicao_anexo=refeicao_anexo_dict,
        )
        warnings: list[str] = []
        if not response.response.strip():
            warnings.append("Resposta de chat vazia.")
        if response.roteamento:
            warnings.extend(response.roteamento.warnings)
        if response.intencao_detectada and response.intencao_detectada.confianca < 0.6:
            warnings.append("Confianca baixa na intencao detectada para roteamento.")
        precisa_revisao = bool(warnings) or bool(response.roteamento and response.roteamento.precisa_revisao)

        tool_name = None
        rag_used = False
        rag_docs_count = 0
        if response.roteamento and isinstance(response.roteamento.metadados, dict):
            tool_name = response.roteamento.metadados.get("tool_name")
            docs = response.roteamento.metadados.get("documentos_rag")
            if isinstance(docs, list):
                rag_docs_count = len(docs)
                rag_used = rag_docs_count > 0
            nested_tool = response.roteamento.metadados.get("tool_metadados")
            if rag_docs_count == 0 and isinstance(nested_tool, dict):
                nested_docs = nested_tool.get("documentos_rag")
                if isinstance(nested_docs, list):
                    rag_docs_count = len(nested_docs)
                    rag_used = rag_docs_count > 0

        self._logger.info(
            "ai_router.chat.integration",
            extra={
                "contexto": "chat",
                "intencao_detectada": (
                    response.intencao_detectada.intencao if response.intencao_detectada else "indefinida"
                ),
                "confianca_intencao": (
                    response.intencao_detectada.confianca if response.intencao_detectada else None
                ),
                "pipeline": response.roteamento.pipeline if response.roteamento else "indefinido",
                "handler": response.roteamento.handler if response.roteamento else "indefinido",
                "status_roteamento": response.roteamento.status if response.roteamento else "indefinido",
                "tool_acionada": tool_name,
                "rag_usado": rag_used,
                "rag_docs_count": rag_docs_count,
                "warnings": len(warnings),
                "precisa_revisao": precisa_revisao,
            },
        )

        return _RouteExecution(
            resultado={
                "contexto": "chat",
                "idioma": idioma,
                "model": response.model,
                "response": response.response,
                "conversation_id": response.conversation_id,
                "memoria": response.memoria.model_dump(exclude_none=True) if response.memoria else None,
                "roteamento": response.roteamento.model_dump(exclude_none=True) if response.roteamento else None,
                "intencao_detectada": (
                    response.intencao_detectada.model_dump(exclude_none=True)
                    if response.intencao_detectada
                    else None
                ),
            },
            warnings=warnings,
            precisa_revisao=precisa_revisao,
            status="parcial" if warnings else "sucesso",
        )

    def _handle_identificar_fotos(self, payload: dict[str, Any], idioma: str) -> _RouteExecution:
        imagem_url = _pick_str(payload, "imagem_url", "image_url")
        if not imagem_url:
            raise ServiceError("Payload invalido para identificar_fotos: informe 'imagem_url'.", status_code=400)

        response = self._foto_alimentos_service.identificar_se_e_foto_de_comida(
            imagem_url=imagem_url,
            contexto="identificar_fotos",
            idioma=idioma,
        )
        confianca = response.resultado_identificacao.confianca or 0.0
        precisa_revisao = (not response.resultado_identificacao.qualidade_adequada) or confianca < 0.75
        warnings: list[str] = []
        if not response.resultado_identificacao.qualidade_adequada:
            warnings.append("Imagem com qualidade inadequada para analise confiavel.")
        if confianca < 0.75:
            warnings.append("Confianca baixa na classificacao da imagem.")

        return _RouteExecution(
            resultado=response.model_dump(exclude_none=True),
            warnings=warnings,
            precisa_revisao=precisa_revisao,
            status="parcial" if warnings else "sucesso",
        )

    def _handle_estimar_porcoes(self, payload: dict[str, Any], idioma: str) -> _RouteExecution:
        imagem_url = _pick_str(payload, "imagem_url", "image_url")
        if not imagem_url:
            raise ServiceError(
                "Payload invalido para estimar_porcoes_do_prato: informe 'imagem_url'.",
                status_code=400,
            )

        response = self._foto_alimentos_service.estimar_porcoes_do_prato(
            imagem_url=imagem_url,
            contexto="estimar_porcoes_do_prato",
            idioma=idioma,
        )
        itens = response.resultado_porcoes.itens
        baixa_confianca = any((item.confianca or 0.0) < 0.7 for item in itens) if itens else True
        faltou_quantidade = any(item.quantidade_estimada_gramas is None for item in itens)
        warnings: list[str] = []
        if not itens:
            warnings.append("Nenhum item alimentar identificado na imagem.")
        if baixa_confianca:
            warnings.append("Uma ou mais porcoes foram estimadas com baixa confianca.")
        if faltou_quantidade:
            warnings.append("Uma ou mais porcoes ficaram sem gramas estimadas.")

        return _RouteExecution(
            resultado=response.model_dump(exclude_none=True),
            warnings=warnings,
            precisa_revisao=bool(warnings),
            status="parcial" if warnings else "sucesso",
        )

    def _handle_transcrever_audio(self, payload: dict[str, Any], idioma: str) -> _RouteExecution:
        audio_base64 = _pick_str(payload, "audio_base64", "arquivo_base64")
        if not audio_base64:
            raise ServiceError(
                "Payload invalido para transcrever_audio_usuario: informe 'audio_base64'.",
                status_code=400,
            )

        nome_arquivo = _pick_str(payload, "nome_arquivo", "file_name") or "audio_usuario.webm"
        audio_bytes = _decode_base64_file(
            encoded=audio_base64,
            file_kind="audio",
            max_bytes=self._settings.audio_max_upload_bytes,
        )

        response = self._audio_transcricao_service.transcrever_audio(
            audio_bytes=audio_bytes,
            nome_arquivo=nome_arquivo,
            contexto="transcrever_audio_usuario",
            idioma=idioma,
        )
        warnings: list[str] = []
        if not response.texto_transcrito.strip():
            warnings.append("Transcricao retornou texto vazio.")
        return _RouteExecution(
            resultado=response.model_dump(exclude_none=True),
            warnings=warnings,
            precisa_revisao=bool(warnings),
            status="parcial" if warnings else "sucesso",
        )

    def _handle_transcrever_pdf(self, payload: dict[str, Any], idioma: str) -> _RouteExecution:
        pdf_base64 = _pick_str(payload, "pdf_base64", "arquivo_base64")
        if not pdf_base64:
            raise ServiceError(
                "Payload invalido para transcrever_texto_pdf: informe 'pdf_base64'.",
                status_code=400,
            )

        nome_arquivo = _pick_str(payload, "nome_arquivo", "file_name") or "documento.pdf"
        pdf_bytes = _decode_base64_file(
            encoded=pdf_base64,
            file_kind="pdf",
            max_bytes=self._settings.pdf_max_upload_bytes,
        )

        response = self._pdf_texto_service.transcrever_pdf(
            pdf_bytes=pdf_bytes,
            nome_arquivo=nome_arquivo,
            contexto="transcrever_texto_pdf",
            idioma=idioma,
        )
        warnings: list[str] = []
        if not response.texto_transcrito.strip():
            warnings.append("Transcricao do PDF retornou texto vazio.")
        return _RouteExecution(
            resultado=response.model_dump(exclude_none=True),
            warnings=warnings,
            precisa_revisao=bool(warnings),
            status="parcial" if warnings else "sucesso",
        )

    def _handle_calcular_calorias(self, payload: dict[str, Any], idioma: str) -> _RouteExecution:
        texto = _pick_str(payload, "texto", "foods", "descricao")
        if not texto:
            raise ServiceError(
                "Payload invalido para calcular_calorias_texto: informe 'texto' (ou 'foods').",
                status_code=400,
            )

        response = self._calorias_texto_service.calcular(
            texto=texto,
            contexto="calcular_calorias_texto",
            idioma=idioma,
        )
        warnings = list(response.warnings)
        if not response.itens:
            warnings.append("Nenhum item alimentar foi identificado para calculo.")
        if response.agente.confianca_media is not None and response.agente.confianca_media < 0.7:
            warnings.append("Confianca media baixa no calculo de calorias.")

        return _RouteExecution(
            resultado=response.model_dump(exclude_none=True),
            warnings=warnings,
            precisa_revisao=bool(warnings),
            status="parcial" if warnings else "sucesso",
        )


def _resolve_trace_id(trace_id: str | None) -> str:
    if trace_id and trace_id.strip():
        return trace_id.strip()
    return uuid.uuid4().hex


def _pick_str(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _pick_bool(payload: dict[str, Any], key: str, *, default: bool) -> bool:
    value = payload.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "sim", "yes"}:
            return True
        if normalized in {"false", "0", "nao", "nÃ£o", "no"}:
            return False
    return default


def _is_timeout_exception(exc: Exception) -> bool:
    current: BaseException | None = exc
    while current is not None:
        name = current.__class__.__name__.lower()
        message = str(current).lower()
        if "timeout" in name or "timed out" in message or "timeout" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


def _decode_base64_file(*, encoded: str, file_kind: str, max_bytes: int) -> bytes:
    # /**** Aceita base64 puro ou data URI (data:...;base64,<conteudo>). ****/
    raw = encoded.strip()
    if ";base64," in raw:
        raw = raw.split(",", 1)[1]
    raw = "".join(raw.split())
    if not raw:
        raise ServiceError(f"Arquivo {file_kind} em base64 esta vazio.", status_code=400)

    try:
        decoded = base64.b64decode(raw, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ServiceError(f"Arquivo {file_kind} em base64 invalido.", status_code=400) from exc

    if len(decoded) > max_bytes:
        raise ServiceError(
            f"Arquivo {file_kind} acima do limite de {max_bytes} bytes.",
            status_code=413,
        )
    return decoded


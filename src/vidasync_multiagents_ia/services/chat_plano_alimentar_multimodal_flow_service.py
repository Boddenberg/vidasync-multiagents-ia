import base64
import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import PlanoAlimentarResponse, PlanoPipelineE2ETesteResponse
from vidasync_multiagents_ia.services.imagem_texto_service import ImagemTextoService
from vidasync_multiagents_ia.services.orchestration.ai_orchestrator import (
    AiOrchestrator,
    PlanoPipelineExecutionInput,
)
from vidasync_multiagents_ia.services.orchestration.factory import build_plano_pipeline_orchestrator
from vidasync_multiagents_ia.services.pdf_texto_service import PdfTextoService
from vidasync_multiagents_ia.services.plano_alimentar_service import PlanoAlimentarService
from vidasync_multiagents_ia.services.plano_texto_normalizado_service import PlanoTextoNormalizadoService


@dataclass(slots=True)
class ChatPlanoAlimentarMultimodalFlowOutput:
    resposta: str
    warnings: list[str] = field(default_factory=list)
    precisa_revisao: bool = False
    metadados: dict[str, Any] = field(default_factory=dict)


class ChatPlanoAlimentarMultimodalFlowService:
    """
    /****
     * Fluxo de plano alimentar no chat para texto, foto e PDF.
     *
     * Responsabilidades:
     * - decidir entre fluxo textual e fluxo multimodal por anexo
     * - acionar pipeline apropriado e consolidar resposta para UX do chat
     * - sinalizar revisao quando houver ambiguidade/incerteza
     *
     * Preparacao para evolucao:
     * - usa o orquestrador de pipeline com engine configuravel (legacy/langgraph)
     * - mantem contrato de saida estavel para integracao com front/judges
     ****/
    """

    def __init__(
        self,
        *,
        settings: Settings,
        plano_texto_normalizado_service: PlanoTextoNormalizadoService | None = None,
        plano_alimentar_service: PlanoAlimentarService | None = None,
        plano_pipeline_orchestrator: AiOrchestrator | None = None,
    ) -> None:
        self._settings = settings
        self._normalizacao_service = plano_texto_normalizado_service or PlanoTextoNormalizadoService(settings=settings)
        self._plano_service = plano_alimentar_service or PlanoAlimentarService(settings=settings)
        self._plano_pipeline_orchestrator = plano_pipeline_orchestrator or build_plano_pipeline_orchestrator(
            settings=settings,
            imagem_service=ImagemTextoService(settings=settings),
            pdf_service=PdfTextoService(settings=settings),
            normalizacao_service=self._normalizacao_service,
            plano_service=self._plano_service,
        )
        self._logger = logging.getLogger(__name__)

    def executar(
        self,
        *,
        prompt: str,
        idioma: str = "pt-BR",
        plano_anexo: dict[str, Any] | None = None,
    ) -> ChatPlanoAlimentarMultimodalFlowOutput:
        started = perf_counter()
        texto = prompt.strip()
        if plano_anexo:
            output = self._executar_fluxo_anexo(prompt=texto, idioma=idioma, plano_anexo=plano_anexo)
        else:
            output = self._executar_fluxo_texto(prompt=texto, idioma=idioma)

        duration_ms = (perf_counter() - started) * 1000.0
        self._logger.info(
            "chat_plano_multimodal_flow.completed",
            extra={
                "modo_execucao": output.metadados.get("modo_execucao"),
                "warnings": len(output.warnings),
                "precisa_revisao": output.precisa_revisao,
                "duration_ms": round(duration_ms, 4),
            },
        )
        return output

    def _executar_fluxo_texto(
        self,
        *,
        prompt: str,
        idioma: str,
    ) -> ChatPlanoAlimentarMultimodalFlowOutput:
        if not _texto_parece_plano(prompt):
            warnings = [
                "Nao identifiquei um plano alimentar completo no texto atual.",
                "Envie o texto integral do plano ou use anexo de foto/PDF para melhor precisao.",
            ]
            return ChatPlanoAlimentarMultimodalFlowOutput(
                resposta=(
                    "Posso interpretar seu plano alimentar, mas preciso do conteudo completo. "
                    "Se preferir, envie foto do plano ou PDF no proprio chat para processar automaticamente."
                ),
                warnings=warnings,
                precisa_revisao=True,
                metadados={
                    "flow": "plano_alimentar_chat_v1",
                    "modo_execucao": "texto",
                    "acao_recomendada": "enviar_texto_completo_ou_anexo",
                },
            )

        normalizado = self._normalizacao_service.normalizar_de_textos(
            textos_fonte=[prompt],
            contexto="normalizar_texto_plano_alimentar",
            idioma=idioma,
        )
        plano = self._plano_service.estruturar_plano(
            textos_fonte=[normalizado.texto_normalizado],
            contexto="estruturar_plano_alimentar",
            idioma=idioma,
        )
        return _build_output_from_plano(
            plano=plano,
            flow="plano_alimentar_chat_v1",
            modo_execucao="texto",
            pipeline_engine=self._settings.plano_pipeline_orchestrator_engine,
            pipeline_etapas=["normalizacao_semantica", "estruturacao_plano"],
        )

    def _executar_fluxo_anexo(
        self,
        *,
        prompt: str,
        idioma: str,
        plano_anexo: dict[str, Any],
    ) -> ChatPlanoAlimentarMultimodalFlowOutput:
        tipo_fonte = str(plano_anexo.get("tipo_fonte") or "").strip().lower()
        if tipo_fonte not in {"imagem", "pdf"}:
            raise ServiceError("Campo 'plano_anexo.tipo_fonte' invalido. Use 'imagem' ou 'pdf'.", status_code=400)

        executar_ocr_literal = _to_bool(plano_anexo.get("executar_ocr_literal"), default=True)
        request = PlanoPipelineExecutionInput(
            tipo_fonte=tipo_fonte,
            contexto="pipeline_chat_plano_alimentar",
            idioma=idioma,
            executar_ocr_literal=executar_ocr_literal,
        )

        if tipo_fonte == "imagem":
            imagem_url = str(plano_anexo.get("imagem_url") or "").strip()
            if not imagem_url:
                raise ServiceError("Campo 'plano_anexo.imagem_url' e obrigatorio para tipo_fonte='imagem'.", status_code=400)
            request.imagem_url = imagem_url
        else:
            pdf_base64 = str(plano_anexo.get("pdf_base64") or "").strip()
            if not pdf_base64:
                raise ServiceError("Campo 'plano_anexo.pdf_base64' e obrigatorio para tipo_fonte='pdf'.", status_code=400)
            request.pdf_bytes = _decode_base64_file(
                encoded=pdf_base64,
                file_kind="pdf",
                max_bytes=self._settings.pdf_max_upload_bytes,
            )
            request.nome_arquivo = str(plano_anexo.get("nome_arquivo") or "plano_alimentar.pdf").strip() or "plano_alimentar.pdf"

        self._logger.info(
            "chat_plano_multimodal_flow.started",
            extra={
                "tipo_fonte": tipo_fonte,
                "prompt_chars": len(prompt),
                "idioma": idioma,
                "executar_ocr_literal": executar_ocr_literal,
                "engine": self._settings.plano_pipeline_orchestrator_engine,
            },
        )

        pipeline_response: PlanoPipelineE2ETesteResponse = self._plano_pipeline_orchestrator.execute_plano_pipeline(
            request=request,
        )
        plano = pipeline_response.plano_estruturado

        output = _build_output_from_plano(
            plano=plano,
            flow="plano_alimentar_chat_v1",
            modo_execucao=f"anexo_{tipo_fonte}",
            pipeline_engine=self._settings.plano_pipeline_orchestrator_engine,
            pipeline_etapas=list(pipeline_response.agente.etapas_executadas),
        )
        output.metadados["pipeline_plano"] = {
            "tipo_fonte": pipeline_response.tipo_fonte,
            "tempos_ms": pipeline_response.tempos_ms.model_dump(exclude_none=True),
            "agente": pipeline_response.agente.model_dump(exclude_none=True),
        }
        return output


def _build_output_from_plano(
    *,
    plano: PlanoAlimentarResponse,
    flow: str,
    modo_execucao: str,
    pipeline_engine: str,
    pipeline_etapas: list[str],
) -> ChatPlanoAlimentarMultimodalFlowOutput:
    warnings = list(plano.plano_alimentar.avisos_extracao)
    refeicoes = len(plano.plano_alimentar.plano_refeicoes)
    precisa_revisao = bool(warnings)

    if precisa_revisao:
        resposta = (
            f"Plano alimentar interpretado com {refeicoes} refeicao(oes), mas existem pontos de revisao. "
            "Revise os itens sinalizados antes de confirmar no app."
        )
    else:
        resposta = (
            f"Plano alimentar interpretado com sucesso: {refeicoes} refeicao(oes) estruturada(s). "
            "Voce pode revisar e confirmar no app."
        )

    return ChatPlanoAlimentarMultimodalFlowOutput(
        resposta=resposta,
        warnings=warnings,
        precisa_revisao=precisa_revisao,
        metadados={
            "flow": flow,
            "modo_execucao": modo_execucao,
            "pipeline_engine": pipeline_engine,
            "pipeline_etapas": pipeline_etapas,
            "plano_alimentar": plano.plano_alimentar.model_dump(exclude_none=True),
            "diagnostico": plano.diagnostico.model_dump(exclude_none=True) if plano.diagnostico else {},
            "normalizacao": {
                "fontes_processadas": plano.fontes_processadas,
            },
        },
    )


def _decode_base64_file(*, encoded: str, file_kind: str, max_bytes: int) -> bytes:
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


def _to_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "sim", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "nao", "não", "no", "n", "off"}:
        return False
    return default


def _texto_parece_plano(prompt: str) -> bool:
    normalized = prompt.lower()
    sinais = ("desjejum", "colacao", "almoco", "jantar", "ceia", "qtd:", "plano alimentar")
    hits = sum(1 for sinal in sinais if sinal in normalized)
    return hits >= 2 or len(prompt.split()) >= 35

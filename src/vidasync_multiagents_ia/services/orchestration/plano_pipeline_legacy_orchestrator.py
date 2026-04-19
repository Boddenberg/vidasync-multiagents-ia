import logging
import re
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from vidasync_multiagents_ia.config import Settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    AgentePlanoPipelineE2ETeste,
    ImagemTextoResponse,
    PdfTextoResponse,
    PlanoPipelineE2ETemposMs,
    PlanoPipelineE2ETesteResponse,
)
from vidasync_multiagents_ia.services.imagem_texto_service import ImagemTextoService
from vidasync_multiagents_ia.services.pdf_texto_service import PdfTextoService
from vidasync_multiagents_ia.services.plano_alimentar_service import PlanoAlimentarService
from vidasync_multiagents_ia.services.plano_texto_normalizado_service import (
    PlanoTextoNormalizadoService,
)
from vidasync_multiagents_ia.services.orchestration.ai_orchestrator import (
    AiOrchestrator,
    PlanoPipelineExecutionInput,
)


class LegacyPlanoPipelineOrchestrator(AiOrchestrator):
    # Engine sequencial (legado): preserva o comportamento atual sem LangGraph.
    def __init__(
        self,
        *,
        settings: Settings,
        imagem_service: ImagemTextoService,
        pdf_service: PdfTextoService,
        normalizacao_service: PlanoTextoNormalizadoService,
        plano_service: PlanoAlimentarService,
    ) -> None:
        self._settings = settings
        self._imagem_service = imagem_service
        self._pdf_service = pdf_service
        self._normalizacao_service = normalizacao_service
        self._plano_service = plano_service
        self._logger = logging.getLogger(__name__)

    def execute_plano_pipeline(self, *, request: PlanoPipelineExecutionInput) -> PlanoPipelineE2ETesteResponse:
        pipeline_id = uuid4().hex
        started = perf_counter()
        etapas_executadas: list[str] = []
        ocr_literal_ms: float | None = None
        ocr_literal: ImagemTextoResponse | PdfTextoResponse | None = None
        textos_ocr_sucesso: list[str] = []
        texto_ocr_pdf: str | None = None

        if request.tipo_fonte not in {"imagem", "pdf"}:
            raise ServiceError("Tipo de fonte invalido para pipeline de plano.", status_code=400)

        self._logger.info(
            "legacy_orchestrator.plano_pipeline.started",
            extra={
                "pipeline_id": pipeline_id,
                "tipo_fonte": request.tipo_fonte,
                "contexto": request.contexto,
                "idioma": request.idioma,
                "executar_ocr_literal": request.executar_ocr_literal,
            },
        )

        if request.tipo_fonte == "imagem" and not request.imagem_url:
            raise ServiceError("Campo 'imagem_url' e obrigatorio para tipo_fonte=imagem.", status_code=400)
        if request.tipo_fonte == "pdf" and (not request.pdf_bytes or not request.nome_arquivo):
            raise ServiceError("Campos 'pdf_bytes' e 'nome_arquivo' sao obrigatorios para tipo_fonte=pdf.", status_code=400)

        if request.executar_ocr_literal:
            t0 = perf_counter()
            if request.tipo_fonte == "imagem":
                ocr_literal = self._imagem_service.transcrever_textos_de_imagens(
                    imagem_urls=[request.imagem_url or ""],
                    contexto="transcrever_texto_imagem",
                    idioma=request.idioma,
                )
                textos_ocr_sucesso = [
                    item.texto_transcrito.strip()
                    for item in ocr_literal.resultados
                    if item.status == "sucesso" and item.texto_transcrito.strip()
                ]
            else:
                ocr_literal = self._pdf_service.transcrever_pdf(
                    pdf_bytes=request.pdf_bytes or b"",
                    nome_arquivo=request.nome_arquivo or "documento.pdf",
                    contexto="transcrever_texto_pdf",
                    idioma=request.idioma,
                )
                texto_ocr_pdf = ocr_literal.texto_transcrito.strip() if ocr_literal.texto_transcrito else None
            ocr_literal_ms = round((perf_counter() - t0) * 1000.0, 4)
            etapas_executadas.append("ocr_literal")

        t1 = perf_counter()
        if request.tipo_fonte == "imagem":
            texto_normalizado = self._normalizar_imagem(
                imagem_url=request.imagem_url or "",
                idioma=request.idioma,
                textos_ocr_sucesso=textos_ocr_sucesso,
            )
        else:
            texto_normalizado = self._normalizar_pdf(
                pdf_bytes=request.pdf_bytes or b"",
                nome_arquivo=request.nome_arquivo or "documento.pdf",
                idioma=request.idioma,
                texto_ocr_pdf=texto_ocr_pdf,
            )
        normalizacao_ms = round((perf_counter() - t1) * 1000.0, 4)
        etapas_executadas.append("normalizacao_semantica")

        t2 = perf_counter()
        plano_estruturado = self._plano_service.estruturar_plano(
            textos_fonte=[texto_normalizado.texto_normalizado],
            contexto="estruturar_plano_alimentar",
            idioma=request.idioma,
        )
        estruturacao_ms = round((perf_counter() - t2) * 1000.0, 4)
        etapas_executadas.append("estruturacao_plano")

        total_ms = round((perf_counter() - started) * 1000.0, 4)
        self._logger.info(
            "legacy_orchestrator.plano_pipeline.completed",
            extra={
                "pipeline_id": pipeline_id,
                "tipo_fonte": request.tipo_fonte,
                "etapas_executadas": etapas_executadas,
                "ocr_literal_ms": ocr_literal_ms,
                "normalizacao_semantica_ms": normalizacao_ms,
                "estruturacao_plano_ms": estruturacao_ms,
                "total_ms": total_ms,
            },
        )

        return PlanoPipelineE2ETesteResponse(
            contexto=request.contexto,
            idioma=request.idioma,
            tipo_fonte=request.tipo_fonte,
            imagem_url=request.imagem_url if request.tipo_fonte == "imagem" else None,
            nome_arquivo=request.nome_arquivo if request.tipo_fonte == "pdf" else None,
            temporario=True,
            ocr_literal=ocr_literal,
            texto_normalizado=texto_normalizado,
            plano_estruturado=plano_estruturado,
            tempos_ms=PlanoPipelineE2ETemposMs(
                ocr_literal_ms=ocr_literal_ms,
                normalizacao_semantica_ms=normalizacao_ms,
                estruturacao_plano_ms=estruturacao_ms,
                total_ms=total_ms,
            ),
            agente=AgentePlanoPipelineE2ETeste(
                contexto="pipeline_teste_plano_e2e",
                nome_agente="agente_pipeline_teste_plano_e2e",
                status="sucesso",
                modelo=self._settings.openai_model,
                pipeline_id=pipeline_id,
                etapas_executadas=etapas_executadas,
                temporario=True,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _normalizar_imagem(
        self,
        *,
        imagem_url: str,
        idioma: str,
        textos_ocr_sucesso: list[str],
    ):
        if textos_ocr_sucesso:
            normalizado_ocr = self._normalizacao_service.normalizar_de_textos(
                textos_fonte=textos_ocr_sucesso,
                contexto="normalizar_texto_plano_alimentar",
                idioma=idioma,
            )
            score_ocr = _score_normalized_text(normalizado_ocr.texto_normalizado)
            if score_ocr < 2:
                normalizado_imagem = self._normalizacao_service.normalizar_de_imagens(
                    imagem_urls=[imagem_url],
                    contexto="normalizar_texto_plano_alimentar",
                    idioma=idioma,
                )
                score_imagem = _score_normalized_text(normalizado_imagem.texto_normalizado)
                return normalizado_imagem if score_imagem >= score_ocr else normalizado_ocr
            return normalizado_ocr

        return self._normalizacao_service.normalizar_de_imagens(
            imagem_urls=[imagem_url],
            contexto="normalizar_texto_plano_alimentar",
            idioma=idioma,
        )

    def _normalizar_pdf(
        self,
        *,
        pdf_bytes: bytes,
        nome_arquivo: str,
        idioma: str,
        texto_ocr_pdf: str | None,
    ):
        if texto_ocr_pdf:
            normalizado_ocr = self._normalizacao_service.normalizar_de_textos(
                textos_fonte=[texto_ocr_pdf],
                contexto="normalizar_texto_plano_alimentar",
                idioma=idioma,
            )
            score_ocr = _score_normalized_text(normalizado_ocr.texto_normalizado)
            if score_ocr < 2:
                normalizado_pdf = self._normalizacao_service.normalizar_de_pdf(
                    pdf_bytes=pdf_bytes,
                    nome_arquivo=nome_arquivo,
                    contexto="normalizar_texto_plano_alimentar",
                    idioma=idioma,
                )
                score_pdf = _score_normalized_text(normalizado_pdf.texto_normalizado)
                return normalizado_pdf if score_pdf >= score_ocr else normalizado_ocr
            return normalizado_ocr

        return self._normalizacao_service.normalizar_de_pdf(
            pdf_bytes=pdf_bytes,
            nome_arquivo=nome_arquivo,
            contexto="normalizar_texto_plano_alimentar",
            idioma=idioma,
        )


def _score_normalized_text(texto: str) -> int:
    lines = [line.strip() for line in texto.splitlines() if line.strip()]
    qtd_alimento = sum(1 for line in lines if re.search(r"(?i)^qtd:\s*.+\|\s*alimento:\s*.+$", line))
    secao_headers = sum(1 for line in lines if re.search(r"^\[[^\]]+\]$", line))
    return (qtd_alimento * 3) + secao_headers

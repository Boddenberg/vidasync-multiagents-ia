import logging
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

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


class _PlanoPipelineState(TypedDict, total=False):
    request: PlanoPipelineExecutionInput
    pipeline_id: str
    etapas_executadas: list[str]
    ocr_literal: ImagemTextoResponse | PdfTextoResponse | None
    textos_ocr_sucesso: list[str]
    texto_ocr_pdf: str | None
    texto_normalizado: Any
    plano_estruturado: Any
    tempos_ms: dict[str, float | None]


class LangGraphPlanoPipelineOrchestrator(AiOrchestrator):
    # Engine LangGraph (piloto): aplica grafo apenas no pipeline de plano alimentar.
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
        self._compiled_graph = self._build_graph()

    def execute_plano_pipeline(self, *, request: PlanoPipelineExecutionInput) -> PlanoPipelineE2ETesteResponse:
        if request.tipo_fonte not in {"imagem", "pdf"}:
            raise ServiceError("Tipo de fonte invalido para pipeline de plano.", status_code=400)
        if request.tipo_fonte == "imagem" and not request.imagem_url:
            raise ServiceError("Campo 'imagem_url' e obrigatorio para tipo_fonte=imagem.", status_code=400)
        if request.tipo_fonte == "pdf" and (not request.pdf_bytes or not request.nome_arquivo):
            raise ServiceError("Campos 'pdf_bytes' e 'nome_arquivo' sao obrigatorios para tipo_fonte=pdf.", status_code=400)

        pipeline_id = uuid4().hex
        started = perf_counter()
        self._logger.info(
            "langgraph_orchestrator.plano_pipeline.started",
            extra={
                "pipeline_id": pipeline_id,
                "tipo_fonte": request.tipo_fonte,
                "contexto": request.contexto,
                "idioma": request.idioma,
                "executar_ocr_literal": request.executar_ocr_literal,
            },
        )

        state = self._compiled_graph.invoke(
            _PlanoPipelineState(
                request=request,
                pipeline_id=pipeline_id,
                etapas_executadas=[],
                textos_ocr_sucesso=[],
                texto_ocr_pdf=None,
                tempos_ms={},
            )
        )

        texto_normalizado = state.get("texto_normalizado")
        plano_estruturado = state.get("plano_estruturado")
        if texto_normalizado is None or plano_estruturado is None:
            raise ServiceError("Falha no pipeline LangGraph de plano alimentar.", status_code=502)

        tempos_ms = state.get("tempos_ms", {})
        total_ms = round((perf_counter() - started) * 1000.0, 4)
        ocr_literal_ms = tempos_ms.get("ocr_literal_ms")
        normalizacao_ms = tempos_ms.get("normalizacao_semantica_ms") or 0.0
        estruturacao_ms = tempos_ms.get("estruturacao_plano_ms") or 0.0
        etapas = state.get("etapas_executadas", [])

        self._logger.info(
            "langgraph_orchestrator.plano_pipeline.completed",
            extra={
                "pipeline_id": pipeline_id,
                "tipo_fonte": request.tipo_fonte,
                "etapas_executadas": etapas,
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
            ocr_literal=state.get("ocr_literal"),
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
                etapas_executadas=etapas,
                temporario=True,
            ),
            extraido_em=datetime.now(timezone.utc),
        )

    def _build_graph(self):
        graph = StateGraph(_PlanoPipelineState)
        graph.add_node("ocr_literal", self._node_ocr_literal)
        graph.add_node("normalizacao_semantica", self._node_normalizacao_semantica)
        graph.add_node("estruturacao_plano", self._node_estruturacao_plano)
        graph.set_entry_point("ocr_literal")
        graph.add_edge("ocr_literal", "normalizacao_semantica")
        graph.add_edge("normalizacao_semantica", "estruturacao_plano")
        graph.add_edge("estruturacao_plano", END)
        return graph.compile()

    def _node_ocr_literal(self, state: _PlanoPipelineState) -> _PlanoPipelineState:
        request = state["request"]
        etapas = list(state.get("etapas_executadas", []))
        tempos = dict(state.get("tempos_ms", {}))

        if not request.executar_ocr_literal:
            tempos["ocr_literal_ms"] = None
            return _PlanoPipelineState(etapas_executadas=etapas, tempos_ms=tempos)

        started = perf_counter()
        ocr_literal: ImagemTextoResponse | PdfTextoResponse | None = None
        textos_ocr_sucesso: list[str] = []
        texto_ocr_pdf: str | None = None

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

        tempos["ocr_literal_ms"] = round((perf_counter() - started) * 1000.0, 4)
        etapas.append("ocr_literal")
        return _PlanoPipelineState(
            ocr_literal=ocr_literal,
            textos_ocr_sucesso=textos_ocr_sucesso,
            texto_ocr_pdf=texto_ocr_pdf,
            etapas_executadas=etapas,
            tempos_ms=tempos,
        )

    def _node_normalizacao_semantica(self, state: _PlanoPipelineState) -> _PlanoPipelineState:
        request = state["request"]
        textos_ocr_sucesso = state.get("textos_ocr_sucesso", [])
        texto_ocr_pdf = state.get("texto_ocr_pdf")
        etapas = list(state.get("etapas_executadas", []))
        tempos = dict(state.get("tempos_ms", {}))
        started = perf_counter()

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

        tempos["normalizacao_semantica_ms"] = round((perf_counter() - started) * 1000.0, 4)
        etapas.append("normalizacao_semantica")
        return _PlanoPipelineState(
            texto_normalizado=texto_normalizado,
            etapas_executadas=etapas,
            tempos_ms=tempos,
        )

    def _node_estruturacao_plano(self, state: _PlanoPipelineState) -> _PlanoPipelineState:
        request = state["request"]
        texto_normalizado = state.get("texto_normalizado")
        if texto_normalizado is None:
            raise ServiceError("Normalizacao semantica nao gerou resultado.", status_code=502)

        etapas = list(state.get("etapas_executadas", []))
        tempos = dict(state.get("tempos_ms", {}))
        started = perf_counter()
        plano_estruturado = self._plano_service.estruturar_plano(
            textos_fonte=[texto_normalizado.texto_normalizado],
            contexto="estruturar_plano_alimentar",
            idioma=request.idioma,
        )
        tempos["estruturacao_plano_ms"] = round((perf_counter() - started) * 1000.0, 4)
        etapas.append("estruturacao_plano")
        return _PlanoPipelineState(
            plano_estruturado=plano_estruturado,
            etapas_executadas=etapas,
            tempos_ms=tempos,
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

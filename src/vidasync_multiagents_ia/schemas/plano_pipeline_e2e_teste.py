from datetime import datetime

from pydantic import BaseModel, Field

from vidasync_multiagents_ia.schemas.imagem_texto import ImagemTextoResponse
from vidasync_multiagents_ia.schemas.pdf_texto import PdfTextoResponse
from vidasync_multiagents_ia.schemas.plano_alimentar import PlanoAlimentarResponse
from vidasync_multiagents_ia.schemas.plano_texto_normalizado import (
    PlanoTextoNormalizadoResponse,
)


class PlanoPipelineE2ETesteJsonRequest(BaseModel):
    contexto: str = "pipeline_teste_plano_e2e"
    idioma: str = "pt-BR"
    imagem_url: str = Field(..., min_length=1)
    executar_ocr_literal: bool = True


class PlanoPipelineE2ETemposMs(BaseModel):
    ocr_literal_ms: float | None = None
    normalizacao_semantica_ms: float
    estruturacao_plano_ms: float
    total_ms: float


class AgentePlanoPipelineE2ETeste(BaseModel):
    contexto: str
    nome_agente: str
    status: str
    modelo: str
    pipeline_id: str
    etapas_executadas: list[str]
    temporario: bool = True


class PlanoPipelineE2ETesteResponse(BaseModel):
    contexto: str
    idioma: str
    tipo_fonte: str
    imagem_url: str | None = None
    nome_arquivo: str | None = None
    temporario: bool = True
    ocr_literal: ImagemTextoResponse | PdfTextoResponse | None = None
    texto_normalizado: PlanoTextoNormalizadoResponse
    plano_estruturado: PlanoAlimentarResponse
    tempos_ms: PlanoPipelineE2ETemposMs
    agente: AgentePlanoPipelineE2ETeste
    extraido_em: datetime

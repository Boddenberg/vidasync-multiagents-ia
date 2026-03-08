from datetime import datetime

from pydantic import BaseModel, Field

from vidasync_multiagents_ia.schemas.imagem_texto import ImagemTextoResponse
from vidasync_multiagents_ia.schemas.plano_alimentar import PlanoAlimentarResponse
from vidasync_multiagents_ia.schemas.plano_texto_normalizado import (
    PlanoTextoNormalizadoResponse,
)


class PlanoImagemPipelineTesteRequest(BaseModel):
    contexto: str = "pipeline_teste_plano_imagem"
    idioma: str = "pt-BR"
    imagem_url: str = Field(..., min_length=1)
    executar_ocr_literal: bool = True


class AgentePlanoImagemPipelineTeste(BaseModel):
    contexto: str
    nome_agente: str
    status: str
    modelo: str
    pipeline_id: str
    etapas_executadas: list[str]


class PlanoImagemPipelineTesteResponse(BaseModel):
    contexto: str
    idioma: str
    imagem_url: str
    ocr_literal: ImagemTextoResponse | None = None
    texto_normalizado: PlanoTextoNormalizadoResponse
    plano_estruturado: PlanoAlimentarResponse
    agente: AgentePlanoImagemPipelineTeste
    extraido_em: datetime

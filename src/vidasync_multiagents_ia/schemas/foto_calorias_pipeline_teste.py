from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field

from vidasync_multiagents_ia.schemas.calorias_texto import CaloriasTextoResponse
from vidasync_multiagents_ia.schemas.foto_alimentos import (
    EstimativaPorcoesFotoResponse,
    IdentificacaoFotoResponse,
    ItemAlimentoEstimado,
)


class FotoCaloriasPipelineTesteRequest(BaseModel):
    contexto: str = "pipeline_teste_foto_calorias"
    idioma: str = "pt-BR"
    imagem_url: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices(
            "imagem_url",
            "image_url",
            "imageUrl",
            "image_key",
            "imageKey",
            "file_key",
            "fileKey",
            "key",
        ),
    )


class FotoCaloriasPipelineTesteTemposMs(BaseModel):
    identificar_foto_ms: float
    estimar_porcoes_ms: float
    calcular_calorias_ms: float
    total_ms: float


class AgenteFotoCaloriasPipelineTeste(BaseModel):
    contexto: str
    nome_agente: str
    status: str
    modelo: str
    pipeline_id: str
    etapas_executadas: list[str]
    precisa_revisao: bool = False


class FotoCaloriasPipelineTesteResponse(BaseModel):
    contexto: str
    idioma: str
    imagem_url: str
    nome_prato_detectado: str | None = None
    composicao: list[ItemAlimentoEstimado] = Field(default_factory=list)
    texto_calorias: str
    identificacao_foto: IdentificacaoFotoResponse
    estimativa_porcoes: EstimativaPorcoesFotoResponse
    calorias_texto: CaloriasTextoResponse
    warnings: list[str] = Field(default_factory=list)
    tempos_ms: FotoCaloriasPipelineTesteTemposMs
    agente: AgenteFotoCaloriasPipelineTeste
    extraido_em: datetime

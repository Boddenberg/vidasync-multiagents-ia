from datetime import datetime

from pydantic import BaseModel, Field


class FrasePorcoesRequest(BaseModel):
    contexto: str = "interpretar_porcoes_texto"
    texto_transcrito: str = Field(min_length=1)
    idioma: str = "pt-BR"
    inferir_quando_ausente: bool = False


class ItemPorcaoTexto(BaseModel):
    nome_alimento: str
    consulta_canonica: str
    quantidade_original: str | None = None
    quantidade_gramas: float | None = None
    quantidade_gramas_min: float | None = None
    quantidade_gramas_max: float | None = None
    origem_quantidade: str = "informada"
    metodo_inferencia: str | None = None
    precisa_revisao: bool = False
    motivo_revisao: str | None = None
    confianca: float | None = None
    observacoes: str | None = None


class ResultadoPorcoesTexto(BaseModel):
    itens: list[ItemPorcaoTexto] = Field(default_factory=list)
    observacoes_gerais: str | None = None


class AgentePorcoesTexto(BaseModel):
    contexto: str
    nome_agente: str
    status: str
    modelo: str
    confianca_media: float | None = None


class FrasePorcoesResponse(BaseModel):
    contexto: str
    texto_transcrito: str
    resultado_porcoes: ResultadoPorcoesTexto
    agente: AgentePorcoesTexto
    extraido_em: datetime

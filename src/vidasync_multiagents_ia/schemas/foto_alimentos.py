from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FotoAgenteRequest(BaseModel):
    contexto: str = "identificar_fotos"
    imagem_url: str = Field(min_length=1)
    idioma: str = "pt-BR"


class IdentificacaoFotoRequest(FotoAgenteRequest):
    contexto: str = "identificar_fotos"


class EstimativaPorcoesFotoRequest(FotoAgenteRequest):
    contexto: str = "estimar_porcoes_do_prato"


class NomePratoFotoRequest(FotoAgenteRequest):
    contexto: str = "identificar_nome_prato_foto"


class ResultadoIdentificacaoFoto(BaseModel):
    eh_comida: bool
    qualidade_adequada: bool
    motivo: str | None = None
    confianca: float | None = None


class ItemAlimentoEstimado(BaseModel):
    nome_alimento: str
    consulta_canonica: str
    quantidade_estimada_gramas: float | None = None
    confianca: float | None = None
    observacoes: str | None = None


class ResultadoPorcoesFoto(BaseModel):
    itens: list[ItemAlimentoEstimado] = Field(default_factory=list)
    observacoes_gerais: str | None = None


class ResultadoNomePratoFoto(BaseModel):
    nome_prato: str | None = None
    confianca: float | None = None
    observacoes: str | None = None


class ExecucaoAgenteFoto(BaseModel):
    contexto: str
    nome_agente: str
    status: str
    modelo: str
    confianca: float | None = None
    saida: dict[str, Any] = Field(default_factory=dict)


class IdentificacaoFotoResponse(BaseModel):
    contexto: str
    imagem_url: str
    resultado_identificacao: ResultadoIdentificacaoFoto
    agente: ExecucaoAgenteFoto
    extraido_em: datetime


class EstimativaPorcoesFotoResponse(BaseModel):
    contexto: str
    imagem_url: str
    resultado_porcoes: ResultadoPorcoesFoto
    agente: ExecucaoAgenteFoto
    extraido_em: datetime


class NomePratoFotoResponse(BaseModel):
    contexto: str
    imagem_url: str
    resultado_nome_prato: ResultadoNomePratoFoto
    agente: ExecucaoAgenteFoto
    extraido_em: datetime

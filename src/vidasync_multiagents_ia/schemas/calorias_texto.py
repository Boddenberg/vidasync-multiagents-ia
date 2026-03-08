from datetime import datetime

from pydantic import BaseModel, Field


class ItemCaloriasTexto(BaseModel):
    descricao_original: str | None = None
    alimento: str
    quantidade_texto: str | None = None
    calorias_kcal: float | None = None
    proteina_g: float | None = None
    carboidratos_g: float | None = None
    lipidios_g: float | None = None
    confianca: float | None = None
    observacoes: str | None = None


class TotaisCaloriasTexto(BaseModel):
    calorias_kcal: float | None = None
    proteina_g: float | None = None
    carboidratos_g: float | None = None
    lipidios_g: float | None = None


class AgenteCaloriasTexto(BaseModel):
    contexto: str
    nome_agente: str
    status: str
    modelo: str
    confianca_media: float | None = None


class CaloriasTextoResponse(BaseModel):
    contexto: str
    idioma: str
    texto: str
    itens: list[ItemCaloriasTexto] = Field(default_factory=list)
    totais: TotaisCaloriasTexto
    warnings: list[str] = Field(default_factory=list)
    agente: AgenteCaloriasTexto
    extraido_em: datetime


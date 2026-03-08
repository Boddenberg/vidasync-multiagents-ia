from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AIRouterRequest(BaseModel):
    trace_id: str | None = None
    contexto: str = Field(min_length=1)
    idioma: str = "pt-BR"
    payload: dict[str, Any] = Field(default_factory=dict)
    metadados: dict[str, Any] = Field(default_factory=dict)


class AIRouterResponse(BaseModel):
    trace_id: str
    contexto: str
    status: Literal["sucesso", "parcial", "erro"]
    warnings: list[str] = Field(default_factory=list)
    precisa_revisao: bool = False
    resultado: dict[str, Any] | None = None
    erro: str | dict[str, Any] | None = None
    extraido_em: datetime


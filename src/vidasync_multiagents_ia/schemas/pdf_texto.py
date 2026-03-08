from datetime import datetime

from pydantic import BaseModel


class AgenteTranscricaoPdf(BaseModel):
    contexto: str
    nome_agente: str
    status: str
    modelo: str


class PdfTextoResponse(BaseModel):
    contexto: str
    idioma: str
    nome_arquivo: str
    texto_transcrito: str
    agente: AgenteTranscricaoPdf
    extraido_em: datetime

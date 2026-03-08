from datetime import datetime

from pydantic import BaseModel


class AgenteTranscricaoAudio(BaseModel):
    contexto: str
    nome_agente: str
    status: str
    modelo: str


class AudioTranscricaoResponse(BaseModel):
    contexto: str
    idioma: str
    nome_arquivo: str
    texto_transcrito: str
    agente: AgenteTranscricaoAudio
    extraido_em: datetime

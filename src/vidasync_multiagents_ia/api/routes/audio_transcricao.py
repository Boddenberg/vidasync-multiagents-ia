from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from vidasync_multiagents_ia.api.dependencies import get_audio_transcricao_service
from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.core import read_upload_with_limit, validate_upload_content_type
from vidasync_multiagents_ia.schemas import AudioTranscricaoResponse
from vidasync_multiagents_ia.services import AudioTranscricaoService

router = APIRouter(prefix="/agentes/audio", tags=["agentes-audio"])

_AUDIO_ALLOWED_CONTENT_TYPES = ("audio/", "application/octet-stream")


@router.post("/transcrever", response_model=AudioTranscricaoResponse)
async def transcrever_audio_usuario(
    audio_file: UploadFile = File(...),
    contexto: str = Form("transcrever_audio_usuario"),
    idioma: str = Form("pt-BR"),
    service: AudioTranscricaoService = Depends(get_audio_transcricao_service),
    settings: Settings = Depends(get_settings),
) -> AudioTranscricaoResponse:
    validate_upload_content_type(
        audio_file,
        allowed_content_types=_AUDIO_ALLOWED_CONTENT_TYPES,
        label="arquivo de audio",
    )
    nome_arquivo = (audio_file.filename or "").strip() or "audio_usuario.webm"
    audio_bytes = await read_upload_with_limit(
        audio_file,
        max_bytes=settings.audio_max_upload_bytes,
        label="arquivo de audio",
    )

    # Executa a transcricao em threadpool (SDK OpenAI sincrono).
    return await run_in_threadpool(
        service.transcrever_audio,
        audio_bytes=audio_bytes,
        nome_arquivo=nome_arquivo,
        contexto=contexto,
        idioma=idioma,
    )

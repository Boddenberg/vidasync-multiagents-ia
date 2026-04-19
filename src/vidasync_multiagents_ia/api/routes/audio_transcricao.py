from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from vidasync_multiagents_ia.api.dependencies import get_audio_transcricao_service
from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import AudioTranscricaoResponse
from vidasync_multiagents_ia.services import AudioTranscricaoService

router = APIRouter(prefix="/agentes/audio", tags=["agentes-audio"])


@router.post("/transcrever", response_model=AudioTranscricaoResponse)
async def transcrever_audio_usuario(
    audio_file: UploadFile = File(...),
    contexto: str = Form("transcrever_audio_usuario"),
    idioma: str = Form("pt-BR"),
    service: AudioTranscricaoService = Depends(get_audio_transcricao_service),
    settings: Settings = Depends(get_settings),
) -> AudioTranscricaoResponse:
    nome_arquivo = (audio_file.filename or "").strip() or "audio_usuario.webm"
    # Leitura com limite para evitar upload gigante em memoria.
    audio_bytes = await _read_upload_with_limit(audio_file, settings.audio_max_upload_bytes)

    # Executa a transcricao em threadpool (SDK OpenAI sincrono).
    return await run_in_threadpool(
        service.transcrever_audio,
        audio_bytes=audio_bytes,
        nome_arquivo=nome_arquivo,
        contexto=contexto,
        idioma=idioma,
    )


async def _read_upload_with_limit(audio_file: UploadFile, max_bytes: int) -> bytes:
    chunk_size = 1024 * 1024
    collected = bytearray()

    while True:
        chunk = await audio_file.read(chunk_size)
        if not chunk:
            break
        collected.extend(chunk)
        if len(collected) > max_bytes:
            raise ServiceError(
                f"Arquivo de audio acima do limite de {max_bytes} bytes.",
                status_code=413,
            )

    return bytes(collected)

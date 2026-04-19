from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from vidasync_multiagents_ia.api.dependencies import get_pdf_texto_service
from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import PdfTextoResponse
from vidasync_multiagents_ia.services import PdfTextoService

router = APIRouter(prefix="/agentes/documentos", tags=["agentes-documentos"])


@router.post("/transcrever-pdf", response_model=PdfTextoResponse)
async def transcrever_pdf(
    pdf_file: UploadFile = File(...),
    contexto: str = Form("transcrever_texto_pdf"),
    idioma: str = Form("pt-BR"),
    service: PdfTextoService = Depends(get_pdf_texto_service),
    settings: Settings = Depends(get_settings),
) -> PdfTextoResponse:
    nome_arquivo = (pdf_file.filename or "").strip() or "documento.pdf"
    _validate_pdf_upload_meta(pdf_file=pdf_file, nome_arquivo=nome_arquivo)

    # Leitura com limite para proteger memoria e evitar payload acima do previsto.
    pdf_bytes = await _read_upload_with_limit(pdf_file, settings.pdf_max_upload_bytes)

    # Executa OCR/transcricao em threadpool porque o cliente OpenAI e sincrono.
    return await run_in_threadpool(
        service.transcrever_pdf,
        pdf_bytes=pdf_bytes,
        nome_arquivo=nome_arquivo,
        contexto=contexto,
        idioma=idioma,
    )


def _validate_pdf_upload_meta(*, pdf_file: UploadFile, nome_arquivo: str) -> None:
    content_type = (pdf_file.content_type or "").lower()
    if content_type and "pdf" not in content_type:
        raise ServiceError("Arquivo invalido: envie um PDF (content-type application/pdf).", status_code=400)

    if not nome_arquivo.lower().endswith(".pdf"):
        raise ServiceError("Arquivo invalido: o nome do arquivo deve terminar com .pdf.", status_code=400)


async def _read_upload_with_limit(pdf_file: UploadFile, max_bytes: int) -> bytes:
    chunk_size = 1024 * 1024
    collected = bytearray()

    while True:
        chunk = await pdf_file.read(chunk_size)
        if not chunk:
            break
        collected.extend(chunk)
        if len(collected) > max_bytes:
            raise ServiceError(
                f"Arquivo PDF acima do limite de {max_bytes} bytes.",
                status_code=413,
            )

    return bytes(collected)

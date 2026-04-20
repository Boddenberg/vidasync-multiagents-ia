from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from vidasync_multiagents_ia.api.dependencies import get_pdf_texto_service
from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.core import read_upload_with_limit, validate_upload_content_type
from vidasync_multiagents_ia.schemas import PdfTextoResponse
from vidasync_multiagents_ia.services import PdfTextoService

router = APIRouter(prefix="/agentes/documentos", tags=["agentes-documentos"])

_PDF_ALLOWED_CONTENT_TYPES = ("pdf", "application/octet-stream")
_PDF_ALLOWED_EXTENSIONS = ("pdf",)


@router.post("/transcrever-pdf", response_model=PdfTextoResponse)
async def transcrever_pdf(
    pdf_file: UploadFile = File(...),
    contexto: str = Form("transcrever_texto_pdf"),
    idioma: str = Form("pt-BR"),
    service: PdfTextoService = Depends(get_pdf_texto_service),
    settings: Settings = Depends(get_settings),
) -> PdfTextoResponse:
    validate_upload_content_type(
        pdf_file,
        allowed_content_types=_PDF_ALLOWED_CONTENT_TYPES,
        allowed_extensions=_PDF_ALLOWED_EXTENSIONS,
        label="arquivo PDF",
    )
    nome_arquivo = (pdf_file.filename or "").strip() or "documento.pdf"
    pdf_bytes = await read_upload_with_limit(
        pdf_file,
        max_bytes=settings.pdf_max_upload_bytes,
        label="arquivo PDF",
    )

    # Executa OCR/transcricao em threadpool porque o cliente OpenAI e sincrono.
    return await run_in_threadpool(
        service.transcrever_pdf,
        pdf_bytes=pdf_bytes,
        nome_arquivo=nome_arquivo,
        contexto=contexto,
        idioma=idioma,
    )

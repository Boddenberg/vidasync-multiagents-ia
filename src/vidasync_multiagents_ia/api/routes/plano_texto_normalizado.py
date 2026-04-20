from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool

from vidasync_multiagents_ia.api.dependencies import get_plano_texto_normalizado_service
from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.core import read_upload_with_limit, validate_upload_content_type
from vidasync_multiagents_ia.schemas import (
    PlanoTextoNormalizadoImagemRequest,
    PlanoTextoNormalizadoResponse,
)
from vidasync_multiagents_ia.services import PlanoTextoNormalizadoService

router = APIRouter(prefix="/agentes/documentos", tags=["agentes-documentos"])

_PDF_ALLOWED_CONTENT_TYPES = ("pdf", "application/octet-stream")
_PDF_ALLOWED_EXTENSIONS = ("pdf",)


@router.post("/normalizar-texto-imagens", response_model=PlanoTextoNormalizadoResponse)
def normalizar_texto_plano_de_imagens(
    payload: PlanoTextoNormalizadoImagemRequest,
    service: PlanoTextoNormalizadoService = Depends(get_plano_texto_normalizado_service),
) -> PlanoTextoNormalizadoResponse:
    return service.normalizar_de_imagens(
        imagem_urls=payload.imagem_urls,
        contexto=payload.contexto,
        idioma=payload.idioma,
    )


@router.post("/normalizar-texto-pdf", response_model=PlanoTextoNormalizadoResponse)
async def normalizar_texto_plano_de_pdf(
    pdf_file: UploadFile = File(...),
    contexto: str = Form("normalizar_texto_plano_alimentar"),
    idioma: str = Form("pt-BR"),
    service: PlanoTextoNormalizadoService = Depends(get_plano_texto_normalizado_service),
    settings: Settings = Depends(get_settings),
) -> PlanoTextoNormalizadoResponse:
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

    return await run_in_threadpool(
        service.normalizar_de_pdf,
        pdf_bytes=pdf_bytes,
        nome_arquivo=nome_arquivo,
        contexto=contexto,
        idioma=idioma,
    )

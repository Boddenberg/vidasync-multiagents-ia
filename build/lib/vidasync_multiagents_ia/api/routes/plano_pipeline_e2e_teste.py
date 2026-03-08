from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from vidasync_multiagents_ia.api.dependencies import get_plano_pipeline_e2e_teste_service
from vidasync_multiagents_ia.config import Settings, get_settings
from vidasync_multiagents_ia.core import ServiceError
from vidasync_multiagents_ia.schemas import (
    PlanoPipelineE2ETesteJsonRequest,
    PlanoPipelineE2ETesteResponse,
)
from vidasync_multiagents_ia.services import PlanoPipelineE2ETesteService

router = APIRouter(prefix="/agentes/debug-local", tags=["agentes-debug-local"])


@router.post("/pipeline-plano-e2e-temporario", response_model=PlanoPipelineE2ETesteResponse)
async def pipeline_plano_e2e_temporario(
    request: Request,
    service: PlanoPipelineE2ETesteService = Depends(get_plano_pipeline_e2e_teste_service),
    settings: Settings = Depends(get_settings),
) -> PlanoPipelineE2ETesteResponse:
    # /**** Endpoint TEMPORARIO: teste ponta a ponta com outputs intermediarios e tempos. ****/
    content_type = (request.headers.get("content-type") or "").lower()

    if "application/json" in content_type:
        payload = PlanoPipelineE2ETesteJsonRequest.model_validate(await request.json())
        return await run_in_threadpool(
            service.executar_pipeline_imagem,
            imagem_url=payload.imagem_url,
            contexto=payload.contexto,
            idioma=payload.idioma,
            executar_ocr_literal=payload.executar_ocr_literal,
        )

    if "multipart/form-data" in content_type:
        form = await request.form()
        tipo_fonte = (str(form.get("tipo_fonte") or "imagem")).strip().lower()
        contexto = (str(form.get("contexto") or "pipeline_teste_plano_e2e")).strip() or "pipeline_teste_plano_e2e"
        idioma = (str(form.get("idioma") or "pt-BR")).strip() or "pt-BR"
        executar_ocr_literal = _parse_form_bool(form.get("executar_ocr_literal"), default=True)

        if tipo_fonte == "imagem":
            imagem_url = (str(form.get("imagem_url") or "")).strip()
            if not imagem_url:
                raise ServiceError("Campo 'imagem_url' e obrigatorio para tipo_fonte=imagem.", status_code=400)
            return await run_in_threadpool(
                service.executar_pipeline_imagem,
                imagem_url=imagem_url,
                contexto=contexto,
                idioma=idioma,
                executar_ocr_literal=executar_ocr_literal,
            )

        if tipo_fonte == "pdf":
            pdf_file = form.get("pdf_file")
            if not isinstance(pdf_file, UploadFile):
                raise ServiceError("Campo 'pdf_file' e obrigatorio para tipo_fonte=pdf.", status_code=400)

            nome_arquivo = (pdf_file.filename or "").strip() or "documento.pdf"
            _validate_pdf_upload_meta(pdf_file=pdf_file, nome_arquivo=nome_arquivo)
            pdf_bytes = await _read_upload_with_limit(pdf_file, settings.pdf_max_upload_bytes)

            return await run_in_threadpool(
                service.executar_pipeline_pdf,
                pdf_bytes=pdf_bytes,
                nome_arquivo=nome_arquivo,
                contexto=contexto,
                idioma=idioma,
                executar_ocr_literal=executar_ocr_literal,
            )

        raise ServiceError("Campo 'tipo_fonte' invalido. Use 'imagem' ou 'pdf'.", status_code=400)

    raise ServiceError(
        "Content-Type invalido. Use application/json (imagem) ou multipart/form-data (imagem/pdf).",
        status_code=415,
    )


def _parse_form_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "sim", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "nao", "não", "no", "n", "off"}:
        return False
    return default


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

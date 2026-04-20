from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_plano_imagem_pipeline_teste_service
from vidasync_multiagents_ia.schemas import (
    PlanoImagemPipelineTesteRequest,
    PlanoImagemPipelineTesteResponse,
)
from vidasync_multiagents_ia.services import PlanoImagemPipelineTesteService

router = APIRouter(prefix="/agentes", tags=["agentes-pipeline"])


@router.post("/pipeline-plano-imagem", response_model=PlanoImagemPipelineTesteResponse)
def pipeline_plano_imagem(
    payload: PlanoImagemPipelineTesteRequest,
    service: PlanoImagemPipelineTesteService = Depends(get_plano_imagem_pipeline_teste_service),
) -> PlanoImagemPipelineTesteResponse:
    # Endpoint temporario para testes locais (facil remover depois).
    return service.executar_pipeline(
        imagem_url=payload.imagem_url,
        contexto=payload.contexto,
        idioma=payload.idioma,
        executar_ocr_literal=payload.executar_ocr_literal,
    )

from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_foto_calorias_pipeline_teste_service
from vidasync_multiagents_ia.schemas import (
    FotoCaloriasPipelineTesteRequest,
    FotoCaloriasPipelineTesteResponse,
)
from vidasync_multiagents_ia.services import FotoCaloriasPipelineTesteService

router = APIRouter(prefix="/agentes", tags=["agentes-pipeline"])


@router.post("/pipeline-foto-calorias", response_model=FotoCaloriasPipelineTesteResponse)
def pipeline_foto_calorias(
    payload: FotoCaloriasPipelineTesteRequest,
    service: FotoCaloriasPipelineTesteService = Depends(get_foto_calorias_pipeline_teste_service),
) -> FotoCaloriasPipelineTesteResponse:
    # Endpoint temporario para teste local de imagem->porcoes->calorias.
    return service.executar_pipeline(
        imagem_url=payload.imagem_url,
        contexto=payload.contexto,
        idioma=payload.idioma,
    )

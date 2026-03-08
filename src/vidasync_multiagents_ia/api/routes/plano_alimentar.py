from fastapi import APIRouter, Depends

from vidasync_multiagents_ia.api.dependencies import get_plano_alimentar_service
from vidasync_multiagents_ia.schemas import PlanoAlimentarRequest, PlanoAlimentarResponse
from vidasync_multiagents_ia.services import PlanoAlimentarService

router = APIRouter(prefix="/agentes/texto", tags=["agentes-texto"])


@router.post("/estruturar-plano-alimentar", response_model=PlanoAlimentarResponse)
def estruturar_plano_alimentar(
    payload: PlanoAlimentarRequest,
    service: PlanoAlimentarService = Depends(get_plano_alimentar_service),
) -> PlanoAlimentarResponse:
    return service.estruturar_plano(
        textos_fonte=payload.textos_fonte,
        contexto=payload.contexto,
        idioma=payload.idioma,
    )
